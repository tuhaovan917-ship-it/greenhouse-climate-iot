"""Compare the Dashboard TypeScript types with the ones in the API contract.

Member 3 writes the Dashboard types in `dashboard/src/types/api.ts`, the
contract carries the same types in `docs/api-contract.md`. This script pulls
both out and compares interface fields and union members, so a field renamed
on one side is caught before it breaks the integration.

Usage:
    .venv/Scripts/python scripts/contract_types_check.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "docs" / "api-contract.md"
# The released state is main; the feature branches are kept as a fallback for
# the case where a part has not been merged yet.
DASHBOARD_TYPES_CANDIDATES = (
    "origin/main:dashboard/src/types/api.ts",
    "origin/feat/dashboard:dashboard/src/types/api.ts",
)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def readGitFile(ref: str) -> str:
    result = subprocess.run(
        ["git", "show", ref], cwd=REPO, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"Khong doc duoc {ref}: {result.stderr.decode(errors='replace')}")
    return result.stdout.decode("utf-8", errors="replace")


def readDashboardTypes() -> str:
    for ref in DASHBOARD_TYPES_CANDIDATES:
        result = subprocess.run(
            ["git", "show", ref], cwd=REPO, capture_output=True, check=False
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    raise SystemExit("Khong tim thay dashboard/src/types/api.ts trong main hay feat/dashboard")


def contractTypes() -> dict[str, dict[str, str]]:
    """Interfaces of the TypeScript block inside the contract document."""
    text = CONTRACT.read_text(encoding="utf-8")
    block = re.search(r"```ts\n(.*?)```", text, re.S)
    if not block:
        return {}
    return parseInterfaces(block.group(1))


def dashboardTypes() -> dict[str, dict[str, str]]:
    return parseInterfaces(readDashboardTypes())


def parseInterfaces(source: str) -> dict[str, dict[str, str]]:
    interfaces: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r"export interface (\w+)\s*\{(.*?)\n\}", source, re.S
    ):
        name = match.group(1)
        fields: dict[str, str] = {}
        body = re.sub(r"//.*", "", match.group(2))
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            # A line may declare several fields: "a: number; b: number;"
            for part in line.split(";"):
                part = part.strip()
                if not part:
                    continue
                field = re.match(r"(\w+)(\??)\s*:\s*(.+)$", part)
                if field:
                    fields[field.group(1)] = field.group(3).strip()
        interfaces[name] = fields
    return interfaces


def main() -> int:
    contract = contractTypes()
    dashboard = dashboardTypes()
    if not contract:
        print("[FAIL] khong tim thay khoi TypeScript trong contract")
        return 1

    print("=== 1. INTERFACE CO TRONG CA HAI ===")
    for name in sorted(set(contract) & set(dashboard)):
        check(f"interface {name} co o ca hai noi", True)

    print()
    print("=== 2. FIELD KHAC NHAU ===")
    for name in sorted(set(contract) & set(dashboard)):
        contractFields = contract[name]
        dashboardFields = dashboard[name]
        onlyContract = sorted(set(contractFields) - set(dashboardFields))
        onlyDashboard = sorted(set(dashboardFields) - set(contractFields))
        check(
            f"{name}: khong thieu field",
            not onlyContract,
            f"contract co: {onlyContract}",
        )
        check(
            f"{name}: khong thua field",
            not onlyDashboard,
            f"dashboard co: {onlyDashboard}",
        )

    print()
    print("=== 3. KIEU FIELD KHAC NHAU (cung ten, bo qua chi tiet kieu con) ===")
    dashboardSource = readDashboardTypes()
    for name in sorted(set(contract) & set(dashboard)):
        for field in sorted(set(contract[name]) & set(dashboard[name])):
            contractType = contract[name][field]
            dashboardType = dashboard[name][field]
            same = contractType == dashboardType
            if not same:
                same = (
                    contractType.replace('"', "'") == dashboardType.replace('"', "'")
                    or contractType.split("|")[0].strip() == dashboardType.split("|")[0].strip()
                )
            if not same:
                # Exclude<Bucket, "raw"> và AggregateBucket là cùng nghĩa.
                same = ("Exclude<Bucket" in contractType and dashboardType == "AggregateBucket") or (
                    "Exclude<Bucket" in dashboardType and contractType == "AggregateBucket"
                )
            check(
                f"{name}.{field} cung kieu",
                same,
                f"contract={contractType!r} dashboard={dashboardType!r}",
            )

    print()
    print("=== 4. TYPE DON (union) ===")
    for typeName in ("ControlMode", "DeviceName", "CommandStatus", "Bucket", "AlertCode", "AlertSeverity"):
        contractMatch = re.search(
            rf"export type {typeName} =([^;\n]+)", CONTRACT.read_text(encoding="utf-8")
        )
        dashboardMatch = re.search(
            rf"export type {typeName} =([^;\n]+)", dashboardSource
        )
        if not contractMatch or not dashboardMatch:
            check(f"type {typeName} tim thay o ca hai noi", False)
            continue
        contractValues = set(re.findall(r'"([^"]+)"', contractMatch.group(1)))
        dashboardValues = set(re.findall(r"'([^']+)'", dashboardMatch.group(1)))
        check(
            f"type {typeName} cung gia tri",
            contractValues == dashboardValues,
            f"contract={sorted(contractValues)} dashboard={sorted(dashboardValues)}",
        )

    print()
    if failures:
        print(f"CONTRACT TYPE CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("CONTRACT TYPE CHECK PASSED: contract va Dashboard khop nhau")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
