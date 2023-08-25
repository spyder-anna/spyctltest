from typing import Dict, List
import zulu
from tabulate import tabulate
import spyctl.spyctl_lib as lib


def time(epoch):
    return zulu.Zulu.fromtimestamp(epoch).format("YYYY-MM-ddTHH:mm:ss") + "Z"


def agent_summary_output(agents: List[Dict]) -> str:
    header = ["NAME", "ID", "HEALTH", "CLUSTER", "ACTIVE BATS"]
    data = []
    for agent in agents:
        data.append(agent_summary_data(agent))
    data.sort(key=lambda line: (calc_health_priority(line[2]), line[0]))
    return tabulate(data, header, tablefmt="plain")


def agent_summary_data(agent: Dict) -> List:
    active_bats = calc_active_bats(agent)
    rv = [
        agent["hostname"],
        agent["id"],
        agent["status"],
        agent.get("cluster_name", lib.NOT_AVAILABLE),
        active_bats,
    ]
    return rv


def agents_output(agents: List[Dict]) -> Dict:
    if len(agents) == 1:
        return agents[0]
    elif len(agents) > 1:
        # Sort the records by hostname, then id, then time
        agents.sort(key=lambda rec: (rec["hostname"], rec["id"], rec["time"]))
        return agents
    else:
        return []


def agent_output_wide_data(agents: Dict, source_data: List[Dict]) -> List:
    active_bats = calc_active_bats(agents)
    matching_data = []
    muid = agents["muid"]
    for item in source_data:
        if muid == item["uid"]:
            rv = [
                agents["hostname"],
                agents["id"],
                agents["status"],
                agents.get("cluster_name", lib.NOT_AVAILABLE),
                active_bats,
                agents["agent_version"],
                time(agents["last_seen"]),
                item["last_data"],
                agents["muid"],
                item["cloud_type"],
                item["cloud_region"],
            ]
            matching_data.append(rv)
    return matching_data


def agents_output_wide(agents: List[Dict], source_data: List[Dict]) -> None:
    header1 = [
        "NAME",
        "ID",
        "HEALTH",
        "CLUSTER",
        "ACTIVE BATS",
        "AGENT VERSION",
        "LAST SEEN",
        "LAST DATA",
        "MUID",
        "CLOUD TYPE",
        "CLOUD REGION",
    ]
    data = []
    for agent in agents:
        data.extend(agent_output_wide_data(agent, source_data))
    data.sort(key=lambda line: (calc_health_priority(line[2]), line[0]))
    print(tabulate(data, header1, tablefmt="plain"))


def calc_active_bats(agent: Dict):
    bat_statuses = agent.get(lib.AGENT_BAT_STATUSES, {})
    total = len(bat_statuses)
    active = 0
    for status in bat_statuses.values():
        if status.get("running", False) is True:
            active += 1
    return f"{active}/{total}"


def calc_health_priority(status):
    return lib.HEALTH_PRIORITY.get(status, 0)


def metrics_ref_map(agents: List[Dict]) -> Dict[str, Dict]:
    rv = {}
    for agent in agents:
        ref_string = f"{agent['id']}:{agent['muid']}"
        rv[ref_string] = agent
    return rv


def metrics_header() -> str:
    columns = [
        "AGENT NAME",
        "AGENT ID",
        "BANDWIDTH BYTES PER SECOND (AVG 1 MINUTE)",
        "CPU USAGE (% OF TIME UTILIZED 1 MINUTE)",
        "MEMORY USAGE BYTES (AVG 1 MINUTE)",
        "CPU CORES",
        "TOTAL MEMORY BYTES",
        "TIME",
    ]
    return ",".join(columns) + "\n"


def metrics_line(metrics_record: Dict, agent_record: Dict) -> str:
    data = [
        agent_record["hostname"],
        agent_record["id"],
        str(metrics_record["bandwidth_1min_Bps"]),
        str(metrics_record["cpu_1min_P"]["agent"]),
        str(metrics_record["mem_1min_B"]["agent"]),
        str(agent_record["num_cores"]),
        str(agent_record.get("total_mem_B", "N/A")),
        str(metrics_record["time"]),
    ]
    return ",".join(data) + "\n"
