import json

import ruamel.yaml


def create_prefix_defs(yaml_conf, prefixes):
    """
    Create separate prefix definitions for the ARTEMIS conf file
    """
    prefix_to_str = {}
    yaml_conf["prefixes"] = ruamel.yaml.comments.CommentedMap()
    for prefix in sorted(prefixes):
        prefix_str = prefixes[prefix]
        prefix_to_str[prefix] = prefix_str
        yaml_conf["prefixes"][prefix_str] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf["prefixes"][prefix_str].append(prefix)
        yaml_conf["prefixes"][prefix_str].yaml_set_anchor(prefix_str)


def create_monitor_defs(yaml_conf):
    """
    Create separate monitor definitions for the ARTEMIS conf file
    """
    yaml_conf["monitors"] = ruamel.yaml.comments.CommentedMap()
    yaml_conf["monitors"]["riperis"] = [""]
    yaml_conf["monitors"]["bgpstreamlive"] = ["routeviews", "ris"]
    yaml_conf["monitors"]["betabmp"] = ["betabmp"]
    # other monitors here


def create_asn_defs(yaml_conf, asns):
    """
    Create separate ASN definitions for the ARTEMIS conf file
    """
    yaml_conf["asns"] = ruamel.yaml.comments.CommentedMap()
    asn_groups = set()
    for asn in sorted(asns):
        asn_group = asns[asn][1]
        if asn_group is not None:
            asn_groups.add(asn_group)
    asn_groups = list(asn_groups)
    for asn_group in sorted(asn_groups):
        yaml_conf["asns"][asn_group] = ruamel.yaml.comments.CommentedSeq()
        yaml_conf["asns"][asn_group].yaml_set_anchor(asn_group)
    for asn in sorted(asns):
        asn_str = asns[asn][0]
        asn_group = asns[asn][1]
        if asn_group is None:
            yaml_conf["asns"][asn_str] = ruamel.yaml.comments.CommentedSeq()
            yaml_conf["asns"][asn_str].append(asn)
            yaml_conf["asns"][asn_str].yaml_set_anchor(asn_str)
        else:
            yaml_conf["asns"][asn_group].append(asn)


def create_rule_defs(yaml_conf, prefixes, asns, prefix_pols):
    """
    Create grouped rule definitions for the ARTEMIS conf file
    """
    yaml_conf["rules"] = ruamel.yaml.comments.CommentedSeq()

    # first derive the prefix rule groups
    # (i.e., which prefixes have the same origin and neighbor)
    prefixes_per_orig_neighb_group = {}
    for prefix in sorted(prefix_pols):
        origin_asns = sorted(list(prefix_pols[prefix]["origins"]))
        neighbors = sorted(list(prefix_pols[prefix]["neighbors"]))
        key = (json.dumps(origin_asns), json.dumps(neighbors))
        if key not in prefixes_per_orig_neighb_group:
            prefixes_per_orig_neighb_group[key] = set()
        prefixes_per_orig_neighb_group[key].add(prefix)

    # then form the actual rules
    for key in sorted(prefixes_per_orig_neighb_group):
        pol_dict = ruamel.yaml.comments.CommentedMap()
        origin_asns = json.loads(key[0])
        neighbors = json.loads(key[1])
        pol_dict["prefixes"] = ruamel.yaml.comments.CommentedSeq()
        for prefix in sorted(prefixes_per_orig_neighb_group[key]):
            pol_dict["prefixes"].append(yaml_conf["prefixes"][prefixes[prefix]])
        pol_dict["origin_asns"] = []
        for asn in origin_asns:
            asn_str = asns[asn][0]
            pol_dict["origin_asns"].append(yaml_conf["asns"][asn_str])
        pol_dict["neighbors"] = []
        neighbor_groups = set()
        for asn in neighbors:
            asn_str = asns[asn][0]
            asn_group = asns[asn][1]
            if asn_group is not None:
                if asn_group not in neighbor_groups:
                    pol_dict["neighbors"].append(yaml_conf["asns"][asn_group])
                    neighbor_groups.add(asn_group)
            else:
                pol_dict["neighbors"].append(yaml_conf["asns"][asn_str])
        pol_dict["mitigation"] = "manual"
        yaml_conf["rules"].append(pol_dict)


def generate_config_yml(prefixes, asns, prefix_pols, yml_file=None):
    """
    Write the config.yaml file content
    """
    with open(yml_file, "w") as f:

        # initial comments
        f.write("#\n")
        f.write("# ARTEMIS Configuration File\n")
        f.write("#\n")
        f.write("\n")

        # initialize conf
        yaml = ruamel.yaml.YAML()
        yaml_conf = ruamel.yaml.comments.CommentedMap()

        # populate conf
        create_prefix_defs(yaml_conf, prefixes)
        create_monitor_defs(yaml_conf)
        create_asn_defs(yaml_conf, asns)
        create_rule_defs(yaml_conf, prefixes, asns, prefix_pols)

        # in-file comments
        yaml_conf.yaml_set_comment_before_after_key(
            "prefixes", before="Start of Prefix Definitions"
        )
        yaml_conf.yaml_set_comment_before_after_key(
            "monitors", before="End of Prefix Definitions"
        )
        yaml_conf.yaml_set_comment_before_after_key("monitors", before="\n")
        yaml_conf.yaml_set_comment_before_after_key(
            "monitors", before="Start of Monitor Definitions"
        )
        yaml_conf.yaml_set_comment_before_after_key(
            "asns", before="End of Monitor Definitions"
        )
        yaml_conf.yaml_set_comment_before_after_key("asns", before="\n")
        yaml_conf.yaml_set_comment_before_after_key(
            "asns", before="Start of ASN Definitions"
        )
        yaml_conf.yaml_set_comment_before_after_key(
            "rules", before="End of ASN Definitions"
        )
        yaml_conf.yaml_set_comment_before_after_key("rules", before="\n")
        yaml_conf.yaml_set_comment_before_after_key(
            "rules", before="Start of Rule Definitions"
        )
        # dump conf
        yaml.dump(yaml_conf, f)

        # end comments
        f.write("# End of Rule Definitions\n")
