"""本地演示数据预置脚本（生长型数据版）。

前置条件：
  1. mock 归因引擎已启动（tools/mock_engine.py，端口 8010）
  2. 遥测服务已按 tools/run_local_demo.ps1 启动（端口 8000，SQLite 演示库）

本脚本按真实工作流的生长方式预置数据：一条 SR 走完整链路
（sr-init → sr-design → 门禁 → ar-split → ar-clarify → 模块设计 → task-split
→ 多个 task-dev），每条 AR 挂真实数目的 task-dev 产出，时间线连续、
人员-仓库-组件-AI Master 归属对应，统计口径（采纳率、双口径、积压体检、
版本名单）都能从这些数据里长出来，而不是孤立拼凑。

数据面覆盖（全部来自同一条生长链路）：
  - 版本运营：多人多版本、升级轨迹、旧版本存量、非发布账号
  - 归因状态：已匹配（多条 task-dev 汇总）、未匹配、退避重试、超窗失败
  - 管理面：等待补丁（未入队）、批量恢复演示位
  - 双口径：一条实验性产出走「申请屏蔽 → 审核通过」链路

用法：python tools/seed_demo_data.py [BASE_URL]
"""

from __future__ import annotations

import hashlib
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ADMIN_PASSWORD = "123456"
client = httpx.Client(base_url=BASE, timeout=30)


def U(tag: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "aaw-demo/" + tag))


def ms(days_ago: float, hour_offset: float = 0.0) -> int:
    when = datetime.now(UTC) - timedelta(days=days_ago) + timedelta(hours=hour_offset)
    return int(when.timestamp() * 1000)


# ---------------------------------------------------------------------------
# 真实 diff：多文件、含生产/测试/配置行，模拟一个有分量的 task-dev 产出
# ---------------------------------------------------------------------------

_FILE_KINDS = {
    "src": ("production_source", False),
    "test": ("test_source", False),
    "sql": ("sql", False),
    "config": ("configuration", False),
}


def make_diff(spec: dict[str, int]) -> bytes:
    """spec: {路径: 新增行数}，生成多文件 unified diff。"""
    parts = []
    for path, added in spec.items():
        parts.append(f"diff --git a/{path} b/{path}")
        parts.append(f"--- a/{path}")
        parts.append(f"+++ b/{path}")
        parts.append(f"@@ -0,0 +1,{added} @@")
        parts += [f"+{path} 第 {i:02d} 行新增实现" for i in range(1, added + 1)]
    return ("\n".join(parts) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 工作流生长：一个 WorkflowRun 由多条消息逐步推进（与真实 CLI 上报一致）
# ---------------------------------------------------------------------------

class Workflow:
    """按真实链路上报一个工作流的全部步骤消息。

    entry=sr:  sr-init → sr-design → sr-design-gate → ar-split
               → ar-clarify → module-boundary-design → module-detail-design-split
               → module-asis-analysis → module-tobe-design → module-test-design
               → module-design-gate → task-split → task-dev × N
    entry=dev: dev-init → dev-design → dev-test-design → dev-design-gate
               → dev-task-split → dev-task-dev × N
    """

    def __init__(
        self,
        tag: str,
        *,
        user_email: str,
        user_name: str,
        version: str,
        sr: str,
        repository: str,
        entry: str = "sr",
        start_days_ago: float,
        step_hours: float = 2.0,
    ):
        self.tag = tag
        self.user_email = user_email
        self.user_name = user_name
        self.version = version
        self.sr = sr
        self.repository = repository
        self.entry = entry
        self.workflow_id = U(f"{tag}-wf")
        self.t0 = start_days_ago  # 工作流开始（days_ago，越小越晚）
        # 工作流 started_at 必须在所有消息间一致：构造时冻结一次，
        # 后续消息复用（每条消息重算会因时钟推进触发 workflow-consistent 校验失败）。
        self.started_ms = ms(start_days_ago)
        self.step_hours = step_hours
        self.step_seq = 0
        self.dev_targets: list[str] = []  # task-dev done 且带 diff 的 message_id

    # -- 时间线：每步间隔 step_hours 小时，工作流随最后一步收口 -----------
    def _clock(self) -> tuple[int, int, int]:
        offset = self.step_seq * self.step_hours
        started = ms(self.t0, hour_offset=offset)
        completed = ms(self.t0, hour_offset=offset + self.step_hours * 0.7)
        updated = completed
        self.step_seq += 1
        return started, completed, updated

    def _sync(
        self,
        step_type: str,
        *,
        ar: str | None,
        status: str = "done",
        diff: bytes | None = None,
        step_name: str | None = None,
        upload: bool | None = None,
    ) -> str | None:
        started, completed, updated = self._clock()
        file_meta = None
        if diff is not None:
            file_meta = {
                "file_name": f"{self.tag}-{step_type}-{self.step_seq}.diff",
                "sha256": hashlib.sha256(diff).hexdigest(),
            }
        payload = {
            "message_id": U(f"{self.tag}-{step_type}-{self.step_seq}"),
            "workflow_id": self.workflow_id,
            "entry": None,  # 服务端按 step_type 推导（sr-init/ar-init/dev-init）
            "aaw_version": self.version,
            "user_email": self.user_email,
            "user_name": self.user_name,
            "repository": self.repository,
            "sr": self.sr,
            "started_at": self.started_ms,
            "completed_at": updated,      # 最后一条消息收口工作流
            "updated_at": updated,
            "data": {
                "ar": ar,
                "step_type": step_type,
                "status": status,
                "started_at": started,
                "completed_at": completed if status == "done" else None,
                "file": file_meta,
            },
        }
        if step_name is not None:
            payload["data"].update({
                "step_id": self.step_seq,
                "step_name": step_name,
                "attempt": 1,
                "execution_type": "skill",
                "skill_names": ["aaw-workflow"],
                "task_id": f"{self.tag}-T{self.step_seq:02d}",
                "development": None,
            })
        response = client.post("/api/v1/telemetry/sync", json=payload)
        response.raise_for_status()
        if diff is not None and (upload if upload is not None else True):
            put = client.put(
                f"/api/v1/objects/step-diffs/{payload['message_id']}",
                content=diff,
                headers={"Content-Type": "application/octet-stream"},
            )
            put.raise_for_status()
            self.dev_targets.append(payload["message_id"])
        return payload["message_id"]

    # -- 真实步骤序列 -------------------------------------------------------

    def run_sr_full(self, ars: list[tuple[str, dict[str, int], str]], *, upload_last: bool = True) -> None:
        """完整 SR 链路。ars: [(AR 号, 每个 task-dev 的 diff spec, 备注)]。

        链路里的设计/门禁步骤真实上报；task-split 后每个 AR 对应
        1~2 个 task-dev（由 ars 条数决定），每个 task-dev 有独立 diff。
        """
        self._sync("sr-init", ar=None, step_name="SR 需求澄清")
        self._sync("sr-design", ar=None, step_name="SR 方案设计")
        self._sync("sr-design-gate", ar=None, step_name="SR 设计门禁")
        # ar-split / ar-clarify / 模块设计链使用第一个 AR 作为流程上下文
        first_ar = ars[0][0]
        self._sync("ar-split", ar=first_ar, step_name="AR 拆分")
        for ar, spec, _note in ars:
            self._sync("ar-clarify", ar=ar, step_name="AR 澄清")
            self._sync("module-boundary-design", ar=ar, step_name="模块边界设计")
            self._sync("module-detail-design-split", ar=ar, step_name="模块详细设计拆分")
            self._sync("module-asis-analysis", ar=ar, step_name="模块现状分析")
            self._sync("module-tobe-design", ar=ar, step_name="模块目标设计")
            self._sync("module-test-design", ar=ar, step_name="模块测试设计")
            self._sync("module-design-gate", ar=ar, step_name="模块设计门禁")
            self._sync("task-split", ar=ar, step_name="任务拆分")
            # task-split 拆出的任务数与 spec 文件数对应（一个任务一个模块面）
            self._sync("task-dev", ar=ar, step_name="任务开发", diff=make_diff(spec))
        _ = upload_last

    def run_dev_light(self, specs: list[dict[str, int]], *, ar: str | None = None) -> None:
        """dev 轻量链路：dev-init → … → dev-task-dev × N。"""
        self._sync("dev-init", ar=ar, step_name="开发启动")
        self._sync("dev-design", ar=ar, step_name="轻量设计")
        self._sync("dev-test-design", ar=ar, step_name="测试设计")
        self._sync("dev-design-gate", ar=ar, step_name="设计门禁")
        self._sync("dev-task-split", ar=ar, step_name="任务拆分")
        for spec in specs:
            self._sync("dev-task-dev", ar=ar, step_name="任务开发", diff=make_diff(spec))


def records() -> dict[str, dict]:
    body = client.get(
        "/api/v1/admin/attribution/records", params={"page_size": 200, "excluded": "all"}
    ).raise_for_status().json()
    return {item["dev_run_id"]: item for item in body["items"]}


def wait_for(expect: dict[str, str], timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client.post("/api/v1/admin/attribution/scan")
        current = records()
        actual = {
            tag: current[msg]["record_status"]
            for tag, msg in seed_targets.items()
            if msg in current
        }
        if all(actual.get(tag) == status for tag, status in expect.items()):
            print(f"  ✓ 归因状态就绪: {expect}")
            return
        time.sleep(1.0)
    raise SystemExit(f"等待超时，当前状态: {actual}，期望: {expect}")


seed_targets: dict[str, str] = {}

print(f"→ 预置生长型演示数据到 {BASE}")

# ═══════════════════════════════════════════════════════════════════
# 数据全景（6 人 × 2 组件 × 3 仓库，AI Master 归属在页面上可配）
#
# 仓库 → 组件:
#   awesome-agent-workflow  → AAW 工具链（李四 SE）
#   telemetry-server        → 遥测平台（张三 SE）
#   telemetry-smoke         → 遥测平台
#
# 人员:
#   张轶渤  2.3.2  SR 链路主力（版本升级轨迹：20 天前 1.1.1 → 现 2.3.2）
#   徐哲威  1.1.1  SR 链路（旧版本存量）
#   宋东方  0.1.0  SR 链路，AR 未匹配 + 实验性产出（双口径演示）
#   张立肖  remote-smoke 版本（非发布账号）
#   赵六    dev 轻量链路（个人开发者）+ 91 天前超窗记录
#   钱九    SR 链路，AR 触发引擎失败（退避重试演示）
#   孙杨宇鑫 dev 链路，补丁未上传（等待补丁演示）
# ═══════════════════════════════════════════════════════════════════

# ── 1. 张轶渤：完整 SR 链路（3 条 AR，各带 task-dev 产出）──────────
# 20 天前旧版本的一次短链路（版本升级轨迹的起点）
wf_zyb_old = Workflow(
    "zyb-v1", user_email="zhangyibo@example.com", user_name="张轶渤",
    version="1.1.1", sr="SR-3001", repository="awesome-agent-workflow",
    start_days_ago=20, step_hours=1.5,
)
wf_zyb_old.run_sr_full([
    ("AR-3001", {"src/api/v2/handler.py": 36, "test/api/v2/test_handler.py": 24}, "接口层"),
])

# 3 天前：主力需求，3 条 AR 全走完（多 task-dev 汇总采纳率）
wf_zyb_main = Workflow(
    "zyb-main", user_email="zhangyibo@example.com", user_name="张轶渤",
    version="2.3.2", sr="SR-3002", repository="awesome-agent-workflow",
    start_days_ago=3, step_hours=1.0,
)
wf_zyb_main.run_sr_full([
    ("AR-3002", {"src/core/engine.py": 48, "src/core/scheduler.py": 32,
                 "test/core/test_engine.py": 26}, "调度核心"),
    ("AR-3003", {"src/api/v2/routes.py": 30, "config/routes.yaml": 12}, "路由配置"),
    ("AR-3004", {"src/web/dashboard.vue": 55, "src/web/api.js": 18}, "看板前端"),
])
seed_targets["zyb_main_ar2"] = wf_zyb_main.dev_targets[0]
seed_targets["zyb_main_ar3"] = wf_zyb_main.dev_targets[1]
seed_targets["zyb_main_ar4"] = wf_zyb_main.dev_targets[2]

# 昨天：第二个需求（SR-3003），跨仓库到遥测平台组件
wf_zyb_ops = Workflow(
    "zyb-ops", user_email="zhangyibo@example.com", user_name="张轶渤",
    version="2.3.2", sr="SR-3005", repository="telemetry-server",
    start_days_ago=1, step_hours=0.8,
)
wf_zyb_ops.run_sr_full([
    ("AR-3005", {"src/aaw_telemetry/routers/ops.py": 42,
                 "test/test_ops.py": 20}, "运营接口"),
])
seed_targets["zyb_ops"] = wf_zyb_ops.dev_targets[0]

# ── 2. 徐哲威：旧版本 SR 链路 ──────────────────────────────────────
wf_xuzw = Workflow(
    "xuzw", user_email="xuzhewei@example.com", user_name="徐哲威",
    version="1.1.1", sr="SR-3006", repository="awesome-agent-workflow",
    start_days_ago=4, step_hours=1.2,
)
wf_xuzw.run_sr_full([
    ("AR-3006", {"src/cli/commands.py": 28, "src/cli/parser.py": 16,
                 "test/test_cli.py": 14}, "CLI 命令"),
])
seed_targets["xuzw"] = wf_xuzw.dev_targets[0]

# ── 3. 宋东方：AR 未匹配 + 实验性产出（双口径演示主角）────────────
wf_songdf = Workflow(
    "songdf", user_email="songdongfang@example.com", user_name="宋东方",
    version="0.1.0", sr="SR-3007", repository="telemetry-smoke",
    start_days_ago=5, step_hours=1.0,
)
wf_songdf.run_sr_full([
    # AR 号含 NOMATCH → mock 引擎返回未匹配（即使有新增行）
    ("AR-3007-NOMATCH", {"src/smoke/case_login.py": 40,
                          "sql/init_schema.sql": 15}, "冒烟用例"),
])
seed_targets["songdf"] = wf_songdf.dev_targets[0]

# ── 4. 张立肖：非发布版本账号（remote-smoke）──────────────────────
wf_zhanglx = Workflow(
    "zhanglx", user_email="zhanglixiao@example.com", user_name="张立肖",
    version="remote-smoke", sr="SR-3008", repository="telemetry-server",
    start_days_ago=1, step_hours=1.0,
)
wf_zhanglx.run_sr_full([
    ("AR-3008", {"src/aaw_telemetry/models.py": 22}, "模型字段"),
])
seed_targets["zhanglx"] = wf_zhanglx.dev_targets[0]

# ── 5. 钱九：引擎故障 → 退避重试（失败分组演示）───────────────────
wf_qian = Workflow(
    "qian", user_email="qianjiu@example.com", user_name="钱九",
    version="2.3.2", sr="SR-3009", repository="awesome-agent-workflow",
    start_days_ago=0.5, step_hours=0.5,
)
wf_qian.run_sr_full([
    ("AR-9009-FAIL", {"src/legacy/adapter.py": 35}, "旧适配器"),
])
seed_targets["qian"] = wf_qian.dev_targets[0]

# ── 6. 赵六：dev 轻量链路 + 超窗失败记录 ──────────────────────────
# 今天：dev 链路正常产出
wf_zhao_dev = Workflow(
    "zhao-dev", user_email="zhaoliu@example.com", user_name="赵六",
    version="2.3.2", sr="SR-3010", repository="telemetry-smoke",
    entry="dev", start_days_ago=0.3, step_hours=0.5,
)
wf_zhao_dev.run_dev_light([
    {"scripts/cleanup.py": 30, "config/cleanup.yaml": 8},
])
seed_targets["zhao_dev"] = wf_zhao_dev.dev_targets[0]

# 91 天前：超出 90 天重试窗口的旧记录（超窗失败 → 强制重跑演示）
wf_zhao_old = Workflow(
    "zhao-old", user_email="zhaoliu@example.com", user_name="赵六",
    version="1.1.1", sr="SR-3011", repository="telemetry-smoke",
    entry="dev", start_days_ago=91, step_hours=1.0,
)
wf_zhao_old.run_dev_light([
    {"src/old_reports.py": 24},
])
seed_targets["zhao_old"] = wf_zhao_old.dev_targets[0]

# 45 天前：仅设计上报（窗口外沉默用户，不进版本名单）
wf_zhao_silent = Workflow(
    "zhao-silent", user_email="zhaoliu@example.com", user_name="赵六",
    version="1.1.1", sr="SR-3012", repository="telemetry-smoke",
    entry="dev", start_days_ago=45, step_hours=1.0,
)
wf_zhao_silent._sync("dev-init", ar=None, step_name="开发启动")
wf_zhao_silent._sync("dev-design", ar=None, step_name="轻量设计")

# ── 7. 孙杨宇鑫：补丁未上传 → 未入队（等待补丁演示）───────────────
wf_sun = Workflow(
    "sun", user_email="sunyangyuxin@example.com", user_name="孙杨宇鑫",
    version="2.3.2", sr="SR-3013", repository="awesome-agent-workflow",
    entry="dev", start_days_ago=0.1, step_hours=0.3,
)
wf_sun.run_dev_light(
    [{"src/tools/seed.py": 26}],
)
# 最后一条 dev-task-dev 已上传；再补一条「带 diff 元数据但不上传」的消息：
# 真实场景是 CLI 上报了 done + 文件信息，但 PUT 补丁失败/中断。
last = wf_sun._sync(
    "dev-task-dev", ar=None, step_name="任务开发（补丁待传）",
    diff=make_diff({"src/tools/seed_extra.py": 18}), upload=False,
)
seed_targets["sun_pending"] = last

print("→ 等待归因调度达到预期状态…")
wait_for({
    "zyb_main_ar2": "finalized_match", "zyb_main_ar3": "finalized_match",
    "zyb_main_ar4": "finalized_match", "zyb_ops": "finalized_match",
    "xuzw": "finalized_match", "songdf": "finalized_no_match",
    "zhanglx": "finalized_match", "qian": "retry_pending",
    "zhao_dev": "finalized_match", "zhao_old": "failed",
    "sun_pending": "not_queued",
})

# ── 8. 实验性产出走完整屏蔽链路（申请 → 审核通过 → 退出统计）───────
print("→ 实验性产出提交屏蔽申请并审核通过（双口径演示）")
login = client.post(
    "/api/v1/anomalies/admin/login", json={"password": ADMIN_PASSWORD}
).raise_for_status().json()
admin_headers = {"X-CSRF-Token": login["csrf_token"]}

request = client.post(
    f"/api/v1/anomalies/targets/dev_run/{seed_targets['songdf']}/archive-requests",
    headers=admin_headers,
    json={"reason": "实验性生成，不以合入为目的", "requested_by": "演示种子"},
).raise_for_status().json()
client.post(
    f"/api/v1/anomalies/archive-requests/{request['id']}/review",
    headers=admin_headers,
    json={"approved": True, "note": "确认为实验性产出"},
).raise_for_status()

# ── 9. 注册表补全 + AI Master 归属（页面同样的操作走 API 一遍）───────
# telemetry-server 仓库注册进遥测平台组件（种子数据在它上面有真实产出）
print("→ 注册 telemetry-server 仓库并配置 AI Master 归属")
client.post(
    "/api/v1/admin/registry/components/telemetry-platform/repos",
    json={
        "repo_key": "telemetry-server",
        "canonical_url": "https://example.invalid/aaw/telemetry-server.git",
        "target_branch": "main",
        "enabled": True,
    },
).raise_for_status()
chain_master = client.post("/api/v1/ai-masters", json={"name": "工具链值守"}).raise_for_status().json()
platform_master = client.post("/api/v1/ai-masters", json={"name": "遥测平台值守"}).raise_for_status().json()
client.put(
    "/api/v1/ai-masters/assignments/aaw-toolchain",
    json={"ai_master_id": chain_master["id"]},
).raise_for_status()
client.put(
    "/api/v1/ai-masters/assignments/telemetry-platform",
    json={"ai_master_id": platform_master["id"]},
).raise_for_status()

# ═══════════════════════════ 数据就绪报告 ═══════════════════════════
current = records()
overview = client.get("/api/v1/dashboard/overview").json()["period"]
roster = client.get("/api/v1/admin/versions/roster").json()
health = client.get("/api/v1/admin/attribution/health").json()

print("\n========== 生长型演示数据就绪 ==========")
print(f"版本基准: {roster['latest_version']}（来源 {roster['release_source']}）"
      f" · 活跃 {roster['active_users']} 人 · 旧版本 {roster['on_old']} 人"
      f" · 非发布账号 {roster['non_release_users']} 人")
print(f"旧版本名单: {[(r['user_name'], r['version'], '落后' + str(r['behind'])) for r in roster['items']]}")
print(f"积压体检: {health['backlog']}")
full_rate = overview["attribution_rate_80"]
intent_rate = overview["attribution_rate_80_merge_intent"]
print(f"双口径: 全量采纳率 {full_rate and round(full_rate, 3)}"
      f" · 合入意图 {intent_rate and round(intent_rate, 3)}"
      f" · 实验性占比 {overview['experimental_share'] and round(overview['experimental_share'], 3)}"
      f" · 已屏蔽 {overview['excluded_lines']} 行")
print("======================================")
print(f"运营后台  {BASE}/admin")
print(f"采纳看板 {BASE}/portal/bright.html")
