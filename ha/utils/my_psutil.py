import os
import psutil
from enum import Enum
import datetime
import time

initial_net_io_counters = psutil.net_io_counters()


def write_speed_test(path="/var/tmp/sd_speed.bin", mb=20) -> float:
    if os.name == "nt":
        path = os.path.join(os.getenv("TEMP", "C:\\Temp"), "sd_speed.bin")

    data = b"x" * (1024 * 1024)
    t0 = time.time()
    with open(path, "wb") as f:
        for _ in range(mb):
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    t = time.time() - t0
    os.remove(path)
    return mb / t  # MB/s


def iso_8601_utc_now(dt: datetime.datetime = datetime.datetime.utcnow()):
    current_datetime_utc = dt
    return current_datetime_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Fields(Enum):
    TIMESTAMP = "timestamp"
    TEMPERATURE = "temperature"
    CPU = "cpu"
    CORE_1 = "core_1"
    CORE_2 = "core_2"
    CORE_3 = "core_3"
    CORE_4 = "core_4"
    CORE_5 = "core_5"
    CORE_6 = "core_6"
    CORE_7 = "core_7"
    CORE_8 = "core_8"

    MEMORY = "memory"
    DISK = "disk"

    TOTAL = "total"
    AVAILABLE = "available"
    USED = "used"
    PERCENT = "percent"

    CPU_FREQ = "cpu_freq"
    CURRENT = "current"
    MIN = "min"
    MAX = "max"

    CPU_PERCENT = "cpu_percent"

    CPU_TIMES_PERCENT = "cpu_times_percent"
    USER = "user"
    NICE = "nice"
    SYSTEM = "system"
    IDLE = "idle"
    IOWAIT = "iowait"

    LOAD = "load"
    MIN_1 = "last1min"
    MIN_5 = "last5min"
    MIN_15 = "last15min"

    NET_IO_COUNTERS = "net_io_counters"
    BYTES_SENT = "bytes_sent"
    BYTES_RECV = "bytes_recv"

    CONTAINERS = "containers"

    PROCESSES = "processes"
    SD_WRITE_SPEED = "sd_write_speed"


class Mypsutil:
    @staticmethod
    def containers():
        try:
            import docker
        except ImportError:
            return {}

        if os.name != "nt":
            client = docker.from_env()
            return {"running": len(client.containers.list())}
        else:
            return {}

    @staticmethod
    def cpu_temp():
        temps = {}
        temp_dict = {}

        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if not temps:
                return temps

            for i, e in enumerate(temps["cpu_thermal"]):
                temp_dict.update({f"core_{i + 1}": e.current})

        return temp_dict

    @staticmethod
    def processes():
        import time

        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
            processes.append(proc)

        time.sleep(1)

        for proc in processes:
            try:
                proc.cpu_percent(interval=None)  # Frissítés
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        processes_info = []
        for proc in processes:
            try:
                info = proc.as_dict(
                    attrs=[
                        "pid",
                        "name",
                        "cpu_percent",
                        "memory_percent",
                        "status",
                        "username",
                    ]
                )
                if info.get("cpu_percent", 0) or 0 > 100:
                    info["cpu_percent"] = (
                        info["cpu_percent"] / psutil.cpu_count()
                    )  # Normalizálás a magok számával
                    processes_info.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        processes_info = sorted(
            processes_info, key=lambda proc: proc["cpu_percent"], reverse=True
        )

        top5_processes: list = []
        for i, proc in enumerate(processes_info[:5]):
            top5_processes.append(
                {
                    "pid": proc["pid"],
                    "name": proc["name"],
                    "cpu_percent": round(proc["cpu_percent"], 2),
                    "memory_percent": round(proc["memory_percent"], 2),
                    "status": proc["status"],
                    "username": proc["username"],
                }
            )

        return top5_processes

    @staticmethod
    def memory():
        memory = psutil.virtual_memory()

        available = round(memory.available / 1024.0 / 1024.0 / 1024.0, 1)
        total = round(memory.total / 1024.0 / 1024.0 / 1024.0, 1)
        used = round(memory.used / 1024.0 / 1024.0 / 1024.0, 1)

        return {
            Fields.AVAILABLE.value: available,
            Fields.TOTAL.value: total,
            Fields.PERCENT.value: memory.percent,
            Fields.USED.value: used,
        }

    @staticmethod
    def disk_info():
        disk = psutil.disk_usage("/")

        available = round(disk.free / 1024.0 / 1024.0 / 1024.0, 1)
        total = round(disk.total / 1024.0 / 1024.0 / 1024.0, 1)
        used = round(disk.used / 1024.0 / 1024.0 / 1024.0, 1)
        return {
            Fields.AVAILABLE.value: available,
            Fields.TOTAL.value: total,
            Fields.USED.value: used,
            Fields.PERCENT.value: disk.percent,
        }

    @staticmethod
    def cpu_load():
        loads = psutil.getloadavg()
        return {
            Fields.MIN_1.value: loads[0] / psutil.cpu_count(),
            Fields.MIN_5.value: loads[1] / psutil.cpu_count(),
            Fields.MIN_15.value: loads[2] / psutil.cpu_count(),
        }

    @staticmethod
    def cpu_freq():
        cpu_freq = psutil.cpu_freq()
        return {
            Fields.CURRENT.value: cpu_freq.current,
            Fields.MIN.value: cpu_freq.min,
            Fields.MAX.value: cpu_freq.max,
        }

    @staticmethod
    def net_io_counters():
        global initial_net_io_counters
        net_io_counters = psutil.net_io_counters()
        bytes_recv = round(
            (net_io_counters.bytes_recv - initial_net_io_counters.bytes_recv)
            / 1024.0
            / 1024.0,
            1,
        )
        bytes_sent = round(
            (net_io_counters.bytes_sent - initial_net_io_counters.bytes_sent)
            / 1024.0
            / 1024.0,
            1,
        )
        initial_net_io_counters = net_io_counters
        return {
            Fields.BYTES_RECV.value: bytes_recv,
            Fields.BYTES_SENT.value: bytes_sent,
        }

    @staticmethod
    def cpu_times_percent():
        cpu_times = psutil.cpu_times_percent()
        if os.name == "nt":
            return {
                Fields.USER.value: cpu_times.user,
                Fields.SYSTEM.value: cpu_times.system,
                Fields.IDLE.value: cpu_times.idle,
            }

        else:
            return {
                Fields.USER.value: cpu_times.user,
                Fields.NICE.value: cpu_times.nice,
                Fields.SYSTEM.value: cpu_times.system,
                Fields.IDLE.value: cpu_times.idle,
                Fields.IOWAIT.value: hasattr(cpu_times, "iowait")
                and cpu_times.iowait
                or 0,
            }

    @staticmethod
    def cpu_percent():
        return psutil.cpu_percent()

    @staticmethod
    def write_speed():
        return {Fields.TOTAL.value: write_speed_test()}

    @classmethod
    def get_all_stat(cls):
        return {
            Fields.CPU_FREQ.value: cls.cpu_freq(),
            Fields.CPU_TIMES_PERCENT.value: cls.cpu_times_percent(),
            Fields.CPU.value: {
                Fields.TEMPERATURE.value: cls.cpu_temp(),
                Fields.PERCENT.value: cls.cpu_percent(),
            },
            Fields.LOAD.value: cls.cpu_load(),
            Fields.DISK.value: cls.disk_info(),
            Fields.MEMORY.value: cls.memory(),
            Fields.NET_IO_COUNTERS.value: cls.net_io_counters(),
            Fields.TIMESTAMP.value: iso_8601_utc_now(),
            Fields.CONTAINERS.value: cls.containers(),
            Fields.PROCESSES.value: cls.processes(),
            Fields.SD_WRITE_SPEED.value: cls.write_speed(),
        }


if __name__ == "__main__":
    import json

    stats = Mypsutil.get_all_stat()
    print(json.dumps(stats, indent=4))
