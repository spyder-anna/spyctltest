import json
import time
import sys
from typing import Dict, List, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import requests
import tqdm
import zulu

import spyctl.cli as cli
import spyctl.spyctl_lib as lib

# Get policy parameters
GET_POL_TYPE = "type"
GET_POL_HAS_TAGS = "has_tags"
GET_POL_NAME_CONTAINS = "name_contains"
GET_POL_POLICY_CONTAINS = "policy_contains"
GET_POL_SELECTOR_CONTAINS = "selector_contains"
GET_POL_UID_EQUALS = "uid_equals"


# https://requests.readthedocs.io/en/latest/user/advanced/#timeouts
# connection timeout, read timeout
TIMEOUT = (30, 300)

AUTO_HIDE_TIME = zulu.now().shift(days=-1)
MAX_TIME_RANGE_SECS = 43200  # 12 hours
NAMESPACES_MAX_RANGE_SECS = 2000
TIMEOUT_MSG = "A timeout occurred during the API request. "


def get(url, key, params=None, raise_notfound=False):
    if key:
        headers = {"Authorization": f"Bearer {key}"}
    else:
        headers = None
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, params=params)
    except requests.exceptions.Timeout as e:
        cli.err_exit(TIMEOUT_MSG + str(*e.args))
    context_uid = r.headers.get("x-context-uid", "No context uid found.")
    if lib.DEBUG:
        print(
            f"Request to {url}\n\tcontext_uid: {context_uid}"
            f"\n\tstatus: {r.status_code}"
        )
    if r.status_code == 404 and raise_notfound:
        raise ValueError
    if r.status_code != 200:
        if "x-context-uid" in r.headers:
            context_uid = r.headers["x-context-uid"]
        else:
            context_uid = "No context uid found."
        msg = [f"{r.status_code}, {r.reason}", f"\tContext UID: {context_uid}"]
        if r.text:
            msg.append(f"{r.text}")
        msg = "\n".join(msg)
        cli.err_exit(msg)
    return r


def post(url, data, key, raise_notfound=False):
    headers = {"Authorization": f"Bearer {key}"}
    try:
        r = requests.post(url, json=data, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout as e:
        cli.err_exit(TIMEOUT_MSG + str(e.args))
    context_uid = r.headers.get("x-context-uid", "No context uid found.")
    if lib.DEBUG:
        print(
            f"Request to {url}\n\tcontext_uid: {context_uid}"
            f"\n\tstatus: {r.status_code}"
        )
    if r.status_code == 404 and raise_notfound:
        raise ValueError
    if r.status_code != 200:
        if "x-context-uid" in r.headers:
            context_uid = r.headers["x-context-uid"]
        else:
            context_uid = "No context uid found."
        msg = [f"{r.status_code}, {r.reason}", f"\tContext UID: {context_uid}"]
        if r.text:
            msg.append(f"{r.text}")
        msg = "\n".join(msg)
        cli.err_exit(msg)
    return r


def put(url, data, key):
    headers = {"Authorization": f"Bearer {key}"}
    try:
        r = requests.put(url, json=data, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout as e:
        cli.err_exit(TIMEOUT_MSG + str(e.args))
    context_uid = r.headers.get("x-context-uid", "No context uid found.")
    if lib.DEBUG:
        print(
            f"Request to {url}\n\tcontext_uid: {context_uid}"
            f"\n\tstatus: {r.status_code}"
        )
    if r.status_code != 200:
        if "x-context-uid" in r.headers:
            context_uid = r.headers["x-context-uid"]
        else:
            context_uid = "No context uid found."
        msg = [f"{r.status_code}, {r.reason}", f"\tContext UID: {context_uid}"]
        if r.text:
            msg.append(f"{r.text}")
        msg = "\n".join(msg)
        cli.err_exit(msg)
    return r


def delete(url, key):
    headers = {"Authorization": f"Bearer {key}"}
    try:
        r = requests.delete(url, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout as e:
        cli.err_exit(TIMEOUT_MSG + str(e.args))
    context_uid = r.headers.get("x-context-uid", "No context uid found.")
    if lib.DEBUG:
        print(
            f"Request to {url}\n\tcontext_uid: {context_uid}"
            f"\n\tstatus: {r.status_code}"
        )
    if r.status_code != 200:
        if "x-context-uid" in r.headers:
            context_uid = r.headers["x-context-uid"]
        else:
            context_uid = "No context uid found."
        msg = [f"{r.status_code}, {r.reason}", f"\tContext UID: {context_uid}"]
        if r.text:
            msg.append(f"{r.text}")
        msg = "\n".join(msg)
        cli.err_exit(msg)
    return r


def time_blocks(
    time_tup: Tuple, max_time_range=MAX_TIME_RANGE_SECS
) -> List[Tuple]:
    """Takes a time tuple (start, end) in epoch time and converts
    it to smaller chunks if necessary.

    Args:
        time_tup (Tuple): start, end

    Returns:
        List[Tuple]: A list of (start, end) tuples to be used in api
            queries
    """
    st, et = time_tup
    if et - st > max_time_range:
        rv = []
        while et - st > max_time_range:
            et2 = min(et, st + max_time_range)
            rv.append((st, et2))
            st = et2
        rv.append((st, et))
        return rv
    else:
        return [time_tup]


def threadpool_progress_bar_time_blocks(
    args_per_thread: List[str],
    time,
    function: Callable,
    max_time_range=MAX_TIME_RANGE_SECS,
    disable_pbar=False,
) -> str:
    """This function runs a multi-threaded task such as making multiple API
    requests simultaneously. By default it shows a progress bar. This is a
    specialized function for the Spyderbat API because it will break up
    api-requests into time blocks of a maximum size if necessary. The
    Spyderbat API doesn't like queries spanning over 24 hours so we break them
    into smaller chunks.

    Args:
        args_per_thread (List[str]): The args to pass to each thread example: list of source uids.
        time (Tuple[float, float]): A tuple containing the start and end time of the task
        function (Callable): The function that each thread will perform
        max_time_range (_type_, optional): The maximum size of a time block. Defaults to MAX_TIME_RANGE_SECS.
        disable_pbar (bool, optional): Disable the progress bar. Defaults to False.

    Yields:
        Iterator[any]: The return value from the thread task.
    """
    t_blocks = time_blocks(time, max_time_range)
    args_per_thread = [
        [arg, t_block] for arg in args_per_thread for t_block in t_blocks
    ]
    pbar = tqdm.tqdm(
        total=len(args_per_thread),
        leave=False,
        file=sys.stderr,
        disable=disable_pbar,
    )
    threads = []
    with ThreadPoolExecutor() as executor:
        for args in args_per_thread:
            threads.append(executor.submit(function, *args))
        for task in as_completed(threads):
            pbar.update(1)
            yield task.result()


def threadpool_progress_bar(
    args_per_thread: List[List], function: Callable, unpack_args=False
):
    pbar = tqdm.tqdm(total=len(args_per_thread), leave=False, file=sys.stderr)
    threads = []
    with ThreadPoolExecutor() as executor:
        for args in args_per_thread:
            if unpack_args:
                threads.append(executor.submit(function, *args))
            else:
                threads.append(executor.submit(function, args))
        for task in as_completed(threads):
            pbar.update(1)
            yield task.result()


# Elastic
def get_object_by_id(
    api_url,
    api_key,
    org_uid,
    id: str,
    schema: str,
    time: Tuple[float, float] = None,
    datatype="spydergraph",
):
    if time:
        hour_floor = lib.truncate_hour_epoch(time[0])
        data = {
            "data_type": datatype,
            "org_uid": org_uid,
            "query": f'(id:"{id}") AND (schema:"{schema}")'
            f" AND ((((valid_to:>{time[0]})"
            f' OR ((NOT status:"closed") AND time:>={hour_floor}))'
            f" AND valid_from:<{time[1]}) OR (time:[{time[0]} TO {time[1]}]"
            f" AND NOT _exists_:valid_to))",
            "query_from": 0,
            "query_size": 1,
        }
    else:
        data = {
            "data_type": datatype,
            "org_uid": org_uid,
            "query": f'(id:"{id}")',
            "query_from": 0,
            "query_size": 1,
        }
    url = (
        f"{api_url}/api/v1/source/query/"
        "?ui_tag=SearchLoadAllSchemaTypesInOneQuery"
    )
    return post(url, data, api_key)


def get_filtered_data(
    api_url,
    api_key,
    org_uid,
    source,
    datatype,
    schema,
    time,
    raise_notfound=False,
    pipeline=None,
    url=None,
):
    if not url:
        url = f"{api_url}/api/v1/source/query/"
    data = {
        "start_time": time[0],
        "end_time": time[1],
        "data_type": datatype,
        "pipeline": [{"filter": {"schema": schema}}, {"latest_model": {}}],
    }
    if org_uid:
        data["org_uid"] = org_uid
    if pipeline:
        data["pipeline"] = pipeline
    if source:
        data["src_uid"] = source
    return post(url, data, api_key, raise_notfound)


def get_audit_events(
    api_url,
    api_key,
    org_uid,
    time,
    src_uid,
    msg_type=None,
    since_id=None,
    disable_pbar: bool = False,
) -> List[Dict]:
    audit_events = []
    if msg_type:
        schema = (
            f"{lib.EVENT_AUDIT_PREFIX}:"
            f"{lib.EVENT_AUDIT_SUBTYPE_MAP[msg_type]}"
        )
    else:
        schema = lib.EVENT_AUDIT_PREFIX
    url = f"{api_url}/api/v1/org/{org_uid}/analyticspolicy/logs"
    for resp in threadpool_progress_bar_time_blocks(
        [src_uid],
        time,
        lambda uid, time_tup: get_filtered_data(
            api_url,
            api_key,
            org_uid,
            uid,
            "audit",
            schema,
            time_tup,
            pipeline=None,
            url=url,
        ),
        disable_pbar=disable_pbar,
    ):
        for event_json in resp.iter_lines():
            event = json.loads(event_json)
            audit_events.append(event)
    audit_events.sort(key=lambda event: event["time"])
    if since_id:
        for i, rec in enumerate(audit_events):
            if rec["id"] == since_id:
                if len(audit_events) > i + 1:
                    ind = i + 1
                    audit_events = audit_events[ind:]
                    break
                else:
                    return []
    return audit_events


def get_audit_events_tail(
    api_url,
    api_key,
    org_uid,
    time,
    src_uid,
    tail: int = -1,  # -1 means all events
    msg_type=None,
    since_id: str = None,
    disable_pbar: bool = False,
) -> List[Dict]:
    audit_events = get_audit_events(
        api_url,
        api_key,
        org_uid,
        time,
        src_uid,
        msg_type,
        since_id,
        disable_pbar=disable_pbar,
    )
    if tail > 0:
        return audit_events[-tail:]
    if tail == 0:
        return []
    else:
        return audit_events


def get_sources_data_for_agents(api_url, api_key, org_uid) -> Dict:
    rv = {}
    url = f"{api_url}/api/v1/org/{org_uid}/source/"
    sources = get(url, api_key).json()
    for source in sources:
        source_uid = source["uid"]  # muid
        if "runtime_details" not in source:
            rv[source_uid] = {
                "uid": source["uid"],
                "cloud_region": lib.NOT_AVAILABLE,
                "cloud_type": lib.NOT_AVAILABLE,
                "last_data": source["last_data"],
            }
        else:
            rv[source_uid] = {
                "uid": source["uid"],
                "cloud_region": source["runtime_details"].get(
                    "cloud_region", lib.NOT_AVAILABLE
                ),
                "cloud_type": source["runtime_details"].get(
                    "cloud_type", lib.NOT_AVAILABLE
                ),
                "last_data": source["last_data"],
            }
    return rv


def get_orgs(api_url, api_key) -> List[Tuple]:
    org_uids = []
    org_names = []
    url = f"{api_url}/api/v1/org/"
    orgs_json = get(url, api_key).json()
    for org in orgs_json:
        org_uids.append(org["uid"])
        org_names.append(org["name"])
    return (org_uids, org_names)


def get_machines(api_url, api_key, org_uid) -> List[Dict]:
    machines: Dict[str, Dict] = {}
    url = f"{api_url}/api/v1/org/{org_uid}/source/"
    source_json = get(url, api_key).json()
    for source in source_json:
        src_uid = source["uid"]
        if not src_uid.startswith("global"):
            machines[src_uid] = source
    # agents API call to find "description" (name used by the UI)
    url = f"{api_url}/api/v1/org/{org_uid}/agent/"
    agent_json = get(url, api_key).json()
    for agent in agent_json:
        src_uid = agent["runtime_details"]["src_uid"]
        description = agent["description"]
        if not agent["uid"].startswith("global"):
            source = machines.get(src_uid)
            if source is None:
                continue
            source.update(agent)
            machine = {}
            machine["uid"] = src_uid
            machine["name"] = description
            del source["uid"]
            del source["description"]
            del source["name"]
            machine.update(source)
            machines[src_uid] = machine
    # Auto-hide inactive machines
    rv = []
    for machine in machines.values():
        if (
            zulu.Zulu.parse(machine["last_data"]) >= AUTO_HIDE_TIME
            or zulu.Zulu.parse(machine["last_stored_chunk_end_time"])
            >= AUTO_HIDE_TIME
        ) and "runtime_details" in machine:
            rv.append(machine)
    return rv


def get_muids(api_url, api_key, org_uid) -> Tuple:
    last_datas = {}
    sources = {}
    # get all sources to get last data
    url = f"{api_url}/api/v1/org/{org_uid}/source/"
    source_json = get(url, api_key).json()
    for source in source_json:
        if not source["uid"].startswith("global"):
            muid = source["uid"]
            last_data = zulu.parse(source["last_data"])
            last_datas[muid] = last_data
    # get agents to get hostnames
    url = f"{api_url}/api/v1/org/{org_uid}/agent/"
    source_json = get(url, api_key).json()
    for source in source_json:
        if not source["uid"].startswith("global"):
            muid = source["runtime_details"]["src_uid"]
            hostname = source["description"]
            if muid in last_datas:
                sources[muid] = {
                    "name": hostname,
                    "last_data": last_datas[muid],
                }
    check_time = zulu.Zulu.fromtimestamp(time.time()).shift(days=-1)
    machines = []
    for muid, data in list(sources.items()):
        if data["last_data"] >= check_time:
            machines.append(
                {
                    "name": data["name"],
                    "uid": muid,
                    "machine_details": {"last_data": str(data["last_data"])},
                }
            )
    return machines


def get_clusters(api_url, api_key, org_uid):
    clusters = []
    url = f"{api_url}/api/v1/org/{org_uid}/cluster/"
    json = get(url, api_key).json()
    for cluster in json:
        if "/" not in cluster["uid"]:
            clusters.append(cluster)
    return clusters


def get_k8s_data(
    api_url, api_key, org_uid, clus_uid, stream, schema_key, time
):
    src = clus_uid + "_" + stream if stream else clus_uid
    url = f"{api_url}/api/v1/org/{org_uid}/data/"
    url += f"?src={src}&st={time[0]}&et={time[1]}&dt=k8s"
    try:
        resp = get_filtered_data(
            api_url,
            api_key,
            org_uid,
            src,
            "k8s",
            schema_key,
            time,
            raise_notfound=bool(stream),
        )
    except ValueError:
        return get_k8s_data(
            api_url, api_key, org_uid, clus_uid, "", schema_key, time
        )
    for k8s_json in resp.iter_lines():
        yield json.loads(k8s_json)


def get_clust_deployments(api_url, api_key, org_uid, clus_uid, time):
    deployments = []
    for data in get_k8s_data(
        api_url,
        api_key,
        org_uid,
        clus_uid,
        "base",
        "model_k8s_deployment",
        time,
    ):
        deployments.append(data)
    return deployments


def get_deployments(api_url, api_key, org_uid, clusters, time):
    deployments = {}
    try:
        for deploy_list in threadpool_progress_bar_time_blocks(
            clusters,
            time,
            lambda cluster, time_block: get_clust_deployments(
                api_url, api_key, org_uid, cluster["uid"], time_block
            ),
        ):
            for deployment in deploy_list:
                uid = deployment["id"]
                version = deployment["version"]
                if (
                    uid not in deployments
                    or version > deployments[uid]["version"]
                ):
                    deployments[uid] = deployment
    except KeyboardInterrupt:
        if deployments:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = [d for d in deployments.values() if d["status"] == "active"]
    return rv


def get_clust_namespaces(api_url, api_key, org_uid, clus_uid, time):
    ns = set()
    for data in get_k8s_data(
        api_url, api_key, org_uid, clus_uid, "base", "model_k8s_cluster", time
    ):
        data_ns = data.get("namespaces", set())
        ns.update(data_ns)
    return (ns, clus_uid)


def get_namespaces(api_url, api_key, org_uid, clusters, time):
    namespaces: Dict[str, set] = defaultdict(set)
    uid_to_name_map = {}
    clusters = [c for c in clusters if "/" not in c["uid"]]
    for cluster in clusters:
        uid_to_name_map[cluster["uid"]] = cluster["name"]
    try:
        for ns_list, uid in threadpool_progress_bar_time_blocks(
            clusters,
            time,
            lambda cluster, time_block: get_clust_namespaces(
                api_url, api_key, org_uid, cluster["uid"], time_block
            ),
            NAMESPACES_MAX_RANGE_SECS,
        ):
            namespaces[uid].update(ns_list)
    except KeyboardInterrupt:
        if namespaces:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = []
    for uid, ns_list in namespaces.items():
        rv.append(
            {
                "cluster_name": uid_to_name_map[uid],
                "cluster_uid": uid,
                "namespaces": ns_list,
            }
        )
    return rv


def get_nodes(api_url, api_key, org_uid, clusters, time) -> List[Dict]:
    nodes = {}
    try:
        for node_list in threadpool_progress_bar_time_blocks(
            clusters,
            time,
            lambda cluster, time_block: get_clust_nodes(
                api_url, api_key, org_uid, cluster["uid"], time_block
            ),
        ):
            for node in node_list:
                id = node["id"]
                version = node["version"]
                if id not in nodes:
                    nodes[id] = node
                else:
                    old_version = nodes[id]["version"]
                    if version > old_version:
                        nodes[id] = node
    except KeyboardInterrupt:
        if nodes:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = list(nodes.values())
    return rv


def get_clust_nodes(api_url, api_key, org_uid, clus_uid, time):
    nodes = {}
    for data in get_k8s_data(
        api_url, api_key, org_uid, clus_uid, "base", "model_k8s_node", time
    ):
        node_id = data["id"]
        if node_id not in nodes:
            nodes[node_id] = data
        elif nodes[node_id]["time"] < data["time"]:
            nodes[node_id] = data
    return list(nodes.values())


def get_pods(api_url, api_key, org_uid, clusters, time) -> List[Dict]:
    pods = {}
    try:
        for pod_list in threadpool_progress_bar_time_blocks(
            clusters,
            time,
            lambda cluster, time_block: get_clust_pods(
                api_url, api_key, org_uid, cluster["uid"], time_block
            ),
        ):
            for pod in pod_list:
                id = pod["id"]
                version = pod["version"]
                if id not in pods:
                    pods[id] = pod
                else:
                    old_version = pods[id]["version"]
                    if version > old_version:
                        pods[id] = pod
    except KeyboardInterrupt:
        if pods:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = list(pods.values())
    return rv


def get_clust_pods(api_url, api_key, org_uid, clus_uid, time):
    pods = {}
    for data in get_k8s_data(
        api_url, api_key, org_uid, clus_uid, "poco", "model_k8s_pod", time
    ):
        pod_id = data["id"]
        if pod_id not in pods:
            pods[pod_id] = data
        elif pods[pod_id]["time"] < data["time"]:
            pods[pod_id] = data
    return list(pods.values())


def get_redflags(api_url, api_key, org_uid, time):
    flags = {}
    try:
        t_blocks = time_blocks(time)
        for resp in threadpool_progress_bar(
            t_blocks,
            lambda t_block: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                "",
                "redflags",
                lib.EVENT_REDFLAG_PREFIX,
                t_block,
            ),
        ):
            for flag_data in resp.iter_lines():
                flag = json.loads(flag_data)
                id = flag["id"]
                version = flag["version"]
                if id not in flags:
                    flags[id] = flag
                else:
                    old_version = flags[id]["version"]
                    if version > old_version:
                        flags[id] = flag
    except KeyboardInterrupt:
        if flags:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = list(flags.values())
    print(rv[0])
    return list(flags.values())


def get_opsflags(api_url, api_key, org_uid, time):
    flags = {}
    try:
        t_blocks = time_blocks(time)
        for resp in threadpool_progress_bar(
            t_blocks,
            lambda t_block: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                "",
                "redflags",
                lib.EVENT_OPSFLAG_PREFIX,
                time,
            ),
        ):
            for flag_data in resp.iter_lines():
                flag = json.loads(flag_data)
                id = flag["id"]
                version = flag["version"]
                if id not in flags:
                    flags[id] = flag
                else:
                    old_version = flags[id]["version"]
                    if version > old_version:
                        flags[id] = flag
    except KeyboardInterrupt:
        if flags:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = list(flags.values())
    return rv


def get_fingerprints(
    api_url, api_key, org_uid, muids, time, fprint_type=None, pipeline=None
):
    fingerprints = {}
    if fprint_type:
        schema = (
            f"{lib.MODEL_FINGERPRINT_PREFIX}:"
            f"{lib.MODEL_FINGERPRINT_SUBTYPE_MAP[fprint_type]}"
        )
    else:
        schema = lib.MODEL_FINGERPRINT_PREFIX
    try:
        for resp in threadpool_progress_bar_time_blocks(
            muids,
            time,
            lambda muid, time_tup: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                muid,
                "fingerprints",
                schema,
                time_tup,
                pipeline=pipeline,
            ),
        ):
            for fprint_json in resp.iter_lines():
                fprint = json.loads(fprint_json)
                if fprint.get("metadata", {}).get("type") not in {
                    lib.POL_TYPE_CONT,
                    lib.POL_TYPE_SVC,
                }:
                    continue
                try:
                    id = fprint["id"]
                    version = fprint["version"]
                    fprint[lib.METADATA_FIELD]["version"] = version
                except Exception:
                    continue
                if id not in fingerprints:
                    fingerprints[id] = fprint
                else:
                    old_fp_version = fingerprints[id][lib.METADATA_FIELD][
                        "version"
                    ]
                    if version > old_fp_version:
                        fingerprints[id] = fprint
    except KeyboardInterrupt:
        if fingerprints:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    rv = list(fingerprints.values())
    return rv


def get_trace_summaries(api_url, api_key, org_uid, muids, time):
    fingerprints = {}
    schema = f"{lib.MODEL_FINGERPRINT_PREFIX}:{lib.POL_TYPE_TRACE}"
    try:
        for resp in threadpool_progress_bar_time_blocks(
            muids,
            time,
            lambda muid, time_tup: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                muid,
                "fingerprints",
                schema,
                time_tup,
            ),
        ):
            for fprint_json in resp.iter_lines():
                try:
                    fprint = json.loads(fprint_json)
                    id = fprint["id"]
                    version = fprint["version"]
                    fprint[lib.METADATA_FIELD]["version"] = version
                except Exception:
                    continue
                if id not in fingerprints:
                    fingerprints[id] = fprint
                else:
                    old_fp_version = fingerprints[id][lib.METADATA_FIELD][
                        "version"
                    ]
                    if version > old_fp_version:
                        fingerprints[id] = fprint
    except KeyboardInterrupt:
        if fingerprints:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    return list(fingerprints.values())


def get_policies(api_url, api_key, org_uid, params=None):
    url = f"{api_url}/api/v1/org/{org_uid}/analyticspolicy/"
    params = {} if params is None else params
    if lib.METADATA_TYPE_FIELD in params:
        types = [params[lib.METADATA_TYPE_FIELD]]
    else:
        types = [lib.POL_TYPE_CONT, lib.POL_TYPE_SVC]
    policies = []
    for type in types:
        params[lib.METADATA_TYPE_FIELD] = type
        resp = get(url, api_key, params)
        for pol_json in resp.iter_lines():
            pol_list = json.loads(pol_json)
            for pol in pol_list:
                uid = pol["uid"]
                policy = json.loads(pol["policy"])
                policy[lib.METADATA_FIELD][lib.METADATA_UID_FIELD] = uid
                policy[lib.METADATA_FIELD][lib.METADATA_CREATE_TIME] = pol[
                    "valid_from"
                ]
                policies.append(policy)
    return policies


def get_policy(api_url, api_key, org_uid, pol_uid):
    url = f"{api_url}/api/v1/org/{org_uid}/analyticspolicy/{pol_uid}"
    resp = get(url, api_key)
    policies = []
    for pol_json in resp.iter_lines():
        pol = json.loads(pol_json)
        uid = pol["uid"]
        policy = pol["policy"]
        policy[lib.METADATA_FIELD][lib.METADATA_UID_FIELD] = uid
        policies.append(policy)
    return policies


def post_new_policy(api_url, api_key, org_uid, data: Dict):
    url = f"{api_url}/api/v1/org/{org_uid}/analyticspolicy/"
    resp = post(url, data, api_key)
    return resp


def put_policy_update(api_url, api_key, org_uid, pol_uid, data: Dict):
    url = f"{api_url}/api/v1/org/{org_uid}/analyticspolicy/{pol_uid}"
    resp = put(url, data, api_key)
    return resp


def delete_policy(api_url, api_key, org_uid, pol_uid):
    url = f"{api_url}/api/v1/org/{org_uid}/analyticspolicy/{pol_uid}"
    resp = delete(url, api_key)
    return resp


def get_source_data(api_url, api_key, org_uid, muids, schema, time):
    for resp in threadpool_progress_bar_time_blocks(
        muids,
        time,
        lambda muid, time_block: get_filtered_data(
            api_url,
            api_key,
            org_uid,
            muid,
            "spydergraph",
            schema,
            time_block,
        ),
    ):
        for json_obj in resp.iter_lines():
            yield json.loads(json_obj)


def get_processes(api_url, api_key, org_uid, muids, time):
    processes = {}
    try:
        for process in get_source_data(
            api_url, api_key, org_uid, muids, "model_process", time
        ):
            id = process["id"]
            version = process["version"]
            if id not in processes:
                processes[id] = process
            else:
                old_version = processes[id]["version"]
                if version > old_version:
                    processes[id] = process
    except KeyboardInterrupt:
        if processes:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    return list(processes.values())


def get_connections(api_url, api_key, org_uid, muids, time):
    connections = {}
    try:
        for connection in get_source_data(
            api_url, api_key, org_uid, muids, "model_connection", time
        ):
            id = connection[lib.ID_FIELD]
            version = connection[lib.VERSION_FIELD]
            if id not in connections:
                connections[id] = connection
            else:
                old_version = connections[id][lib.VERSION_FIELD]
                if version > old_version:
                    connections[id] = connection
    except KeyboardInterrupt:
        if connections:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    return list(connections.values())


def get_spydertraces(api_url, api_key, org_uid, muids, time):
    spydertraces = {}
    try:
        for spydertrace in get_source_data(
            api_url, api_key, org_uid, muids, "model_spydertrace", time
        ):
            id = spydertrace[lib.ID_FIELD]
            version = spydertrace[lib.VERSION_FIELD]
            if id not in spydertraces:
                spydertraces[id] = spydertrace
            else:
                old_version = spydertraces[id][lib.VERSION_FIELD]
                if version > old_version:
                    spydertraces[id] = spydertrace
    except KeyboardInterrupt:
        if spydertraces:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    return list(spydertraces.values())


def get_containers(api_url, api_key, org_uid, muids, time):
    containers = {}
    try:
        for container in get_source_data(
            api_url, api_key, org_uid, muids, "model_container", time
        ):
            id = container["id"]
            version = container["version"]
            if id not in containers:
                containers[id] = container
            else:
                old_version = containers[id]["version"]
                if version > old_version:
                    containers[id] = container
    except KeyboardInterrupt:
        if containers:
            __log_interrupt_partial()
        else:
            __log_interrupt()
    return list(containers.values())


def get_agents(
    api_url, api_key, org_uid, sources: List[str], time, pipeline=None
):
    agents = {}
    try:
        for resp in threadpool_progress_bar_time_blocks(
            sources,
            time,
            lambda source, time_tup: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                source,
                "agent_status",
                "model_agent",
                time_tup,
                pipeline=pipeline,
            ),
        ):
            for json_obj in resp.iter_lines():
                agent = json.loads(json_obj)
                version = agent["version"]
                id = agent["id"]
                if id not in agents:
                    agents[id] = agent
                else:
                    old_version = agents[id]["version"]
                    if version > old_version:
                        agents[id] = agent
    except KeyboardInterrupt:
        __log_interrupt()
    return list(agents.values())


def get_agent_metrics(
    api_url,
    api_key,
    org_uid,
    sources: List[str],
    time,
    pipeline=None,
    disable_pbar=False,
):
    try:
        for resp in threadpool_progress_bar_time_blocks(
            sources,
            time,
            lambda source, time_tup: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                source,
                "agent_status",
                "event_agentmetrics",
                time_tup,
                pipeline=pipeline,
            ),
            disable_pbar=disable_pbar,
        ):
            for json_obj in resp.iter_lines():
                metrics_record = json.loads(json_obj)
                yield metrics_record
    except KeyboardInterrupt:
        __log_interrupt()


def get_latest_agent_metrics(
    api_url,
    api_key,
    org_uid,
    args: List[Tuple[str, Tuple]],  # list (source_uid, (st, et))
    pipeline=None,
):
    try:
        for resp in threadpool_progress_bar(
            args,
            lambda source, time_tup: get_filtered_data(
                api_url,
                api_key,
                org_uid,
                source,
                "agent_status",
                "event_agentmetrics",
                time_tup,
                pipeline=pipeline,
            ),
            unpack_args=True,
        ):
            latest_time = 0
            for json_obj in reversed(list(resp.iter_lines())):
                metrics_record = json.loads(json_obj)
                time = metrics_record["time"]
                if time <= latest_time:
                    break
                else:
                    latest_time = time
                yield metrics_record
    except KeyboardInterrupt:
        __log_interrupt()


def __log_interrupt_partial():
    cli.try_log("\nRequest aborted, partial results retrieved.")


def __log_interrupt():
    cli.try_log("\nRequest aborted, no partial results.. exiting.")
    exit(0)


def get_pypi_version():
    url = "https://pypi.org/pypi/spyctl/json"
    try:
        resp = get(url, key=None, raise_notfound=True)
        version = resp.json().get("info", {}).get("version")
        if not version:
            # cli.try_log("Unable to parse latest pypi version")
            return None
        return version
    except ValueError:
        # cli.try_log("Unable to reach version API")
        pass


# Spyctl api test functions


def api_create_guardian_policy(
    api_url, api_key, org_uid, name, mode, data: Dict
) -> str:
    url = f"{api_url}/api/v1/org/{org_uid}/spyctl/guardianpolicy/build/"
    data = {"input_objects": json.dumps([data]), "mode": mode}
    if name:
        data["name"] = name
    resp = post(url, data, api_key)
    policy = resp.json()["policy"]
    return policy


def api_create_suppression_policy(
    api_url,
    api_key,
    org_uid,
    name,
    type,
    scope_to_users,
    object_uid,
    **selectors,
) -> str:
    url = f"{api_url}/api/v1/org/{org_uid}/spyctl/suppressionpolicy/build/"
    data = {"type": type}

    def dash(key: str) -> str:
        return key.replace("_", "-")

    processed_selectors = {dash(k): v for k, v in selectors.items()}
    if name:
        data["name"] = name
    if scope_to_users:
        data["scope_to_users"] = scope_to_users
    if object_uid:
        data["object_uid"] = object_uid
    if processed_selectors:
        data["selectors"] = processed_selectors
    print(data)
    resp = post(url, data, api_key)
    policy = resp.json()["policy"]
    return policy


def api_merge(api_url, api_key, org_uid, obj, m_objs):
    url = f"{api_url}/api/v1/org/{org_uid}/spyctl/merge/"
    data = {"merge_objects": json.dumps([m_objs]), "object": json.dumps(obj)}
    resp = post(url, data, api_key)
    merged_object = resp.json()["merged_object"]
    return merged_object


def api_diff(api_url, api_key, org_uid, obj, d_objs):
    url = f"{api_url}/api/v1/org/{org_uid}/spyctl/diff/"
    data = {"diff_objects": json.dumps([d_objs]), "object": json.dumps(obj)}
    resp = post(url, data, api_key)
    diff_data = resp.json()["diff_data"]
    return diff_data


def api_validate(api_url, api_key, org_uid, data: Dict) -> str:
    url = f"{api_url}/api/v1/org/{org_uid}/spyctl/validate/"
    resp = post(url, data, api_key)
    invalid_msg = resp.json()["invalid_message"]
    return invalid_msg
