import hashlib
import json
import logging.config
import logging.handlers
import os
import re
import time
from contextlib import contextmanager
from ipaddress import ip_network as str2ip
from logging.handlers import SMTPHandler

import psycopg2
import yaml

SUPERVISOR_HOST = os.getenv("SUPERVISOR_HOST", "localhost")
SUPERVISOR_PORT = os.getenv("SUPERVISOR_PORT", 9001)
DB_NAME = os.getenv("DB_NAME", "artemis_db")
DB_USER = os.getenv("DB_USER", "artemis_user")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_PASS = os.getenv("DB_PASS", "Art3m1s")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", 5672)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", 6379)

RABBITMQ_URI = "amqp://{}:{}@{}:{}//".format(
    RABBITMQ_USER, RABBITMQ_PASS, RABBITMQ_HOST, RABBITMQ_PORT
)
SUPERVISOR_URI = "http://{}:{}/RPC2".format(SUPERVISOR_HOST, SUPERVISOR_PORT)


class TLSSMTPHandler(SMTPHandler):
    def emit(self, record):
        """
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib

            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg,
            )
            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.starttls()  # for tls add this line
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


class SSLSMTPHandler(SMTPHandler):
    def emit(self, record):
        """
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib

            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(record),
                formatdate(),
                msg,
            )
            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


def get_logger(path="/etc/artemis/logging.yaml"):
    if os.path.exists(path):
        with open(path, "r") as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
        log = logging.getLogger("artemis_logger")
        log.info("Loaded configuration from {}".format(path))
    else:
        FORMAT = "%(module)s - %(asctime)s - %(levelname)s @ %(funcName)s: %(message)s"
        logging.basicConfig(format=FORMAT, level=logging.INFO)
        log = logging
        log.info("Loaded default configuration")
    return log


log = get_logger()


@contextmanager
def get_ro_cursor(conn):
    with conn.cursor() as curr:
        try:
            yield curr
        except Exception:
            raise


@contextmanager
def get_wo_cursor(conn):
    with conn.cursor() as curr:
        try:
            yield curr
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()


def get_db_conn():
    conn = None
    time_sleep_connection_retry = 5
    while not conn:
        try:
            conn = psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                host=DB_HOST,
                port=DB_PORT,
                password=DB_PASS,
            )
        except Exception:
            log.exception("exception")
            time.sleep(time_sleep_connection_retry)
        finally:
            log.debug("PostgreSQL DB created/connected..")
    return conn


def flatten(items, seqtypes=(list, tuple)):
    res = []
    if not isinstance(items, seqtypes):
        return [items]
    for item in items:
        if isinstance(item, seqtypes):
            res += flatten(item)
        else:
            res.append(item)
    return res


class ArtemisError(Exception):
    def __init__(self, _type, _where):
        self.type = _type
        self.where = _where

        message = "type: {}, at: {}".format(_type, _where)

        # Call the base class constructor with the parameters it needs
        super().__init__(message)


def exception_handler(log):
    def function_wrapper(f):
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception:
                log.exception("exception")
                return True

        return wrapper

    return function_wrapper


def dump_json(json_obj, filename):
    with open(filename, "w") as f:
        json.dump(json_obj, f)


def redis_key(prefix, hijack_as, _type):
    assert isinstance(prefix, str)
    assert isinstance(hijack_as, int)
    assert isinstance(_type, str)
    return get_hash([prefix, hijack_as, _type])


def get_hash(obj):
    return hashlib.shake_128(yaml.dump(obj).encode("utf-8")).hexdigest(16)


def purge_redis_eph_pers_keys(redis_instance, ephemeral_key, persistent_key):
    redis_pipeline = redis_instance.pipeline()
    # purge also tokens since they are not relevant any more
    redis_pipeline.delete("{}token_active".format(ephemeral_key))
    redis_pipeline.delete("{}token".format(ephemeral_key))
    redis_pipeline.delete(ephemeral_key)
    redis_pipeline.srem("persistent-keys", persistent_key)
    redis_pipeline.delete("hij_orig_neighb_{}".format(ephemeral_key))
    if redis_instance.exists("hijack_{}_prefixes_peers".format(ephemeral_key)):
        for element in redis_instance.sscan_iter(
            "hijack_{}_prefixes_peers".format(ephemeral_key)
        ):
            subelems = element.decode().split("_")
            prefix_peer_hijack_set = "prefix_{}_peer_{}_hijacks".format(
                subelems[0], subelems[1]
            )
            redis_pipeline.srem(prefix_peer_hijack_set, ephemeral_key)
            if redis_instance.scard(prefix_peer_hijack_set) <= 1:
                redis_pipeline.delete(prefix_peer_hijack_set)
        redis_pipeline.delete("hijack_{}_prefixes_peers".format(ephemeral_key))
    redis_pipeline.execute()


def valid_prefix(input_prefix):
    try:
        str2ip(input_prefix)
    except Exception:
        return False
    return True


def calculate_more_specifics(prefix, min_length, max_length):
    prefix_list = []
    for prefix_length in range(min_length, max_length + 1):
        prefix_list.extend(prefix.subnets(new_prefix=prefix_length))
    return prefix_list


class SetEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, set):
            return list(o)
        return super(SetEncoder, self).default(o)


def translate_rfc2622(input_prefix, just_match=False):
    """
    :param input_prefix: (str) input IPv4/IPv6 prefix that
    should be translated according to RFC2622
    :param just_match: (bool) check only if the prefix
    has matched instead of translating
    :return: output_prefixes: (list of str) output IPv4/IPv6 prefixes,
    if not just_match, otherwise True or False
    """

    # ^- is the exclusive more specifics operator; it stands for the more
    #    specifics of the address prefix excluding the address prefix
    #    itself.  For example, 128.9.0.0/16^- contains all the more
    #    specifics of 128.9.0.0/16 excluding 128.9.0.0/16.
    reg_exclusive = re.match(r"^(\S*)\^-$", input_prefix)
    if reg_exclusive:
        matched_prefix = reg_exclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen + 1
            max_length = matched_prefix_ip.max_prefixlen
            if just_match:
                return True
            return list(
                map(
                    str,
                    calculate_more_specifics(matched_prefix_ip, min_length, max_length),
                )
            )

    # ^+ is the inclusive more specifics operator; it stands for the more
    #    specifics of the address prefix including the address prefix
    #    itself.  For example, 5.0.0.0/8^+ contains all the more specifics
    #    of 5.0.0.0/8 including 5.0.0.0/8.
    reg_inclusive = re.match(r"^(\S*)\^\+$", input_prefix)
    if reg_inclusive:
        matched_prefix = reg_inclusive.group(1)
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = matched_prefix_ip.prefixlen
            max_length = matched_prefix_ip.max_prefixlen
            if just_match:
                return True
            return list(
                map(
                    str,
                    calculate_more_specifics(matched_prefix_ip, min_length, max_length),
                )
            )

    # ^n where n is an integer, stands for all the length n specifics of
    #    the address prefix.  For example, 30.0.0.0/8^16 contains all the
    #    more specifics of 30.0.0.0/8 which are of length 16 such as
    #    30.9.0.0/16.
    reg_n = re.match(r"^(\S*)\^(\d+)$", input_prefix)
    if reg_n:
        matched_prefix = reg_n.group(1)
        length = int(reg_n.group(2))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            min_length = length
            max_length = length
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError("invalid-n-small", input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError("invalid-n-large", input_prefix)
            if just_match:
                return True
            return list(
                map(
                    str,
                    calculate_more_specifics(matched_prefix_ip, min_length, max_length),
                )
            )

    # ^n-m where n and m are integers, stands for all the length n to
    #      length m specifics of the address prefix.  For example,
    #      30.0.0.0/8^24-32 contains all the more specifics of 30.0.0.0/8
    #      which are of length 24 to 32 such as 30.9.9.96/28.
    reg_n_m = re.match(r"^(\S*)\^(\d+)-(\d+)$", input_prefix)
    if reg_n_m:
        matched_prefix = reg_n_m.group(1)
        min_length = int(reg_n_m.group(2))
        max_length = int(reg_n_m.group(3))
        if valid_prefix(matched_prefix):
            matched_prefix_ip = str2ip(matched_prefix)
            if min_length < matched_prefix_ip.prefixlen:
                raise ArtemisError("invalid-n-small", input_prefix)
            if max_length > matched_prefix_ip.max_prefixlen:
                raise ArtemisError("invalid-n-large", input_prefix)
            if just_match:
                return True
            return list(
                map(
                    str,
                    calculate_more_specifics(matched_prefix_ip, min_length, max_length),
                )
            )

    # nothing has matched
    if just_match:
        return False

    return [input_prefix]


def translate_asn_range(asn_range, just_match=False):
    """
    :param <str> asn_range: <start_asn>-<end_asn>
    :param <bool> just_match: check only if the prefix
    has matched instead of translating
    :return: the list of ASNs corresponding to that range
    """
    reg_range = re.match(r"(\d+)\s*-\s*(\d+)", str(asn_range))
    if reg_range:
        start_asn = int(reg_range.group(1))
        end_asn = int(reg_range.group(2))
        if start_asn > end_asn:
            raise ArtemisError("end-asn before start-asn", asn_range)
        if just_match:
            return True
        return list(range(start_asn, end_asn + 1))

    # nothing has matched
    if just_match:
        return False

    return [asn_range]
