"""
批量测试运行器 — 遍历 tests/scripts/ 执行所有脚本并聚合报告。

用法:
    python tests/scripts/run_all.py --app CustomerApp.exe
    python tests/scripts/run_all.py --app CustomerApp.exe --filter 新建客户
    python tests/scripts/run_all.py --app CustomerApp.exe --report-path report.json
    python tests/scripts/run_all.py --report-only tests/scripts/_report.json
"""
import sys, os, json, glob, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from services.automation_service import execute_script

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")

def main():
    parser = argparse.ArgumentParser(description="批量运行自动化测试脚本")
    parser.add_argument("--app", help="Delphi 应用 exe 路径")
    parser.add_argument("--filter", default="", help="按名称过滤脚本（如: 新建客户）")
    parser.add_argument("--report-path", help="执行后输出报告到 JSON 文件")
    parser.add_argument("--report-only", help="读取已有报告 JSON 并打印摘要，不执行脚本")
    args = parser.parse_args()

    if args.report_only:
        with open(args.report_only, "r", encoding="utf-8") as f:
            summary = json.load(f)
        print_summary(summary)
        return 0 if summary.get("total_failed", 0) == 0 else 1

    if not args.app:
        parser.error("--app is required unless --report-only is used")

    scripts = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.json")))
    if args.filter:
        scripts = [s for s in scripts if args.filter in os.path.basename(s)]

    if not scripts:
        print(f"未找到测试脚本: {SCRIPTS_DIR}")
        return 1

    print(f"找到 {len(scripts)} 个脚本\n")
    all_reports = []
    total_pass = total_fail = 0

    for sp in scripts:
        name = os.path.splitext(os.path.basename(sp))[0]
        with open(sp, "r", encoding="utf-8") as f:
            script_data = json.load(f)

        steps = script_data.get("steps", [])
        print(f"[运行] {name} ({len(steps)} 步)...", end=" ", flush=True)

        result = execute_script(args.app, steps, keep_alive=True)
        report = result.get("report", {})
        all_reports.append({
            "script": name,
            "status": result.get("status"),
            "report": report,
            "first_failure": report.get("first_failure"),
            "solution": report.get("solution"),
        })

        pf = f"✅ {report.get('passed')}/{report.get('total')}" if report.get('failed', 0) == 0 else f"❌ {report.get('passed')}/{report.get('total')}"
        print(f"{pf}  {report.get('success_rate')}  {report.get('duration_seconds', 0)}s")
        total_pass += report.get("passed", 0)
        total_fail += report.get("failed", 0)

    # 输出报告 JSON
    total = total_pass + total_fail
    summary = {
        "total_scripts": len(all_reports),
        "total_steps": total,
        "total_passed": total_pass,
        "total_failed": total_fail,
        "success_rate": f"{total_pass/total*100:.0f}%" if total else "0%",
        "scripts": all_reports,
    }
    print_summary(summary)

    report_path = args.report_path or os.path.join(SCRIPTS_DIR, "_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"报告已保存: {report_path}")

    return 0 if total_fail == 0 else 1


def print_summary(summary):
    """Print a compact report summary."""
    total = summary.get("total_steps", 0)
    passed = summary.get("total_passed", 0)
    print(f"\n{'='*50}")
    if total:
        print(
            "汇总: {} 脚本, {}/{} 通过 ({})".format(
                summary.get("total_scripts", 0),
                passed,
                total,
                summary.get("success_rate", "0%"),
            )
        )
    else:
        print("汇总: 0 步")

    for script in summary.get("scripts", []):
        failure = script.get("first_failure")
        if failure:
            print(
                "首个失败: {} #{} {} {} -> {}".format(
                    script.get("script", ""),
                    failure.get("index", 0),
                    failure.get("cmd", ""),
                    failure.get("target", ""),
                    failure.get("signal", ""),
                )
            )

if __name__ == "__main__":
    sys.exit(main())
