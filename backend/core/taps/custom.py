from kombu import Connection
from kombu import Exchange
from kombu import Producer
from utils import get_logger
from utils import RABBITMQ_URI
import sys
import json
import time

log = get_logger()


def run():
    def runner():
        with open(sys.argv[1]) as json_file:
            data = json.load(json_file)
            for i in range(7):
                msg_ = {
                    "timestamp": data['bgp_update'][i]['timestamp'],
                    "orig_path": data['bgp_update'][i]['orig_path'],
                    "communities": data['bgp_update'][i]['communities'],
                    "service": data['bgp_update'][i]['service'],
                    "type": data['bgp_update'][i]['type'],
                    "path": data['bgp_update'][i]['path'],
                    "prefix": data['bgp_update'][i]['prefix'],
                    "peer_asn": data['bgp_update'][i]['peer_asn'],
                }
                with Connection(RABBITMQ_URI) as connection:
                    exchange = Exchange(
                        "bgp-update", channel=connection, type="direct", durable=False
                    )
                    exchange.declare()
                    with Producer(connection) as producer:
                        msg_["key"] = "{}".format(i+50)
                        print (msg_)
                        producer.publish(
                            msg_, exchange=exchange, routing_key="update", serializer="json"
                        )
                time.sleep(15)

    import threading

    threads = []
    for i in range(1):
        threads.append(threading.Thread(target=runner,))
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("exception")
    except KeyboardInterrupt:
        pass
