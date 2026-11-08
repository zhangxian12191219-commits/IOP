#!/usr/bin/env python3
"""商业授权码生成工具（仅销售方持有私钥时使用）。

示例：
    python tools/license_generator.py \
      --private-key license_private_key.pem \
      --licensee "某某科技有限公司" \
      --machine-code 1234-ABCD-... \
      --max-assets 100 \
      --expires 2027-12-31

不要把 license_private_key.pem 放进安装包或交付给客户。
"""
import argparse
import base64
import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


FEATURE_CATALOG = {
    "assets": "资产管理与 SNMP 采集",
    "topology": "网络拓扑",
    "bigscreen": "大屏展示",
    "website": "网站监控（含 HTTPS 证书、批量导入与状态码）",
    "rooms": "机房管理与 3D 数字孪生",
    "im": "即时通信与音视频通话",
    "inspection": "设备巡检",
    "credentials": "设备凭据（巡检/备份共用）",
    "mib": "MIB 管理",
    "ai": "AI智能运维（对话、分析、报告与AI大屏）",
    "cascade": "总部分支级联（加密隧道、分支数据与级联通信）",
    "cluster": "集群与负载均衡",
    "network": "主机网络配置",
    "virtualization": "虚拟化管理（VMware / H3C CAS / KVM）",
    "tools": "系统工具",
    "alerts": "告警中心",
    "audit": "审计日志",
    "backup": "数据库与系统备份",
    "config_backup": "网络设备配置备份",
    "log_forward": "日志转发",
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
try:
    PRODUCT_VERSION = str(
        json.loads((PROJECT_ROOT / "backend" / "version.json").read_text(encoding="utf-8")).get("version")
        or "2.21.24"
    )
except Exception:
    PRODUCT_VERSION = "2.21.24"
PLATFORM_VERSION = "2.10.0"

EDITION_PRESETS = {
    "opensource": {
        "label": "开源版",
        "features": list(FEATURE_CATALOG.keys()),
        "max_assets": 50,
        "max_nodes": 1,
        "price_per_asset": 0,
    },
    "commercial": {
        "label": "商业版",
        "features": list(FEATURE_CATALOG.keys()),
        "max_assets": 100,
        "max_nodes": 3,
        "price_per_asset": 100,
    },
}

def main() -> None:
    parser = argparse.ArgumentParser(description="生成网管系统商业授权码（软件授权签发平台）")
    parser.add_argument("--private-key", help="Ed25519 私钥 PEM 文件路径（离线保管）")
    parser.add_argument("--licensee", help="授权客户名称")
    parser.add_argument("--machine-code", help="系统「授权信息」页面显示的机器码")
    parser.add_argument("--max-assets", type=int, help="允许的资产数量；留空使用版本默认值（开源 50 / 商业 100）")
    parser.add_argument("--max-nodes", type=int, help="允许的集群节点数；留空使用版本默认值（开源 1 / 商业 3）")
    parser.add_argument("--expires", default="", help="到期日期 YYYY-MM-DD；留空表示永久")
    parser.add_argument("--edition", default="opensource", choices=list(EDITION_PRESETS), help="授权版本")
    parser.add_argument(
        "--features", default="",
        help="逗号分隔的功能模块；留空按 edition 预设",
    )
    parser.add_argument("--list-features", action="store_true", help="列出可签发功能模块")
    parser.add_argument("--list-editions", action="store_true", help="列出套餐预设")
    parser.add_argument("--platform-version", action="version", version=f"授权签发平台 v{PLATFORM_VERSION} / 产品 v{PRODUCT_VERSION}")
    args = parser.parse_args()
    if args.list_features:
        for key, name in FEATURE_CATALOG.items():
            print(f"{key:14s} {name}")
        return
    if args.list_editions:
        for key, item in EDITION_PRESETS.items():
            print(f"{key:12s} {item['label']}: {', '.join(item['features'])}")
        return
    if not args.private_key or not args.licensee or not args.machine_code:
        raise SystemExit("签发授权需要 --private-key / --licensee / --machine-code")
    preset = EDITION_PRESETS[args.edition]
    max_assets = args.max_assets if args.max_assets is not None else int(preset["max_assets"])
    if max_assets <= 0:
        raise SystemExit("资产数量必须大于 0")
    max_nodes = args.max_nodes if args.max_nodes is not None else int(preset["max_nodes"])
    if max_nodes <= 0:
        raise SystemExit("集群节点数必须大于 0")
    if args.features.strip():
        features = [item.strip() for item in args.features.split(",") if item.strip()]
        unknown = [item for item in features if item not in FEATURE_CATALOG]
        if unknown:
            raise SystemExit(f"未知功能模块：{', '.join(unknown)}；可用模块：{', '.join(FEATURE_CATALOG)}")
    else:
        features = list(EDITION_PRESETS[args.edition]["features"])
    machine_id = args.machine_code.replace("-", "").strip().lower()
    if len(machine_id) != 32:
        raise SystemExit("机器码应为 32 位十六进制（可带连字符）")
    now = datetime.now(timezone.utc)
    # 默认永久；指定到期日期时按北京时间当日 23:59:59 计算。
    expires_at = None
    duration_days = None
    if args.expires.strip():
        try:
            expire_date = datetime.strptime(args.expires.strip(), "%Y-%m-%d").date()
            expire_dt = datetime.combine(
                expire_date, time(23, 59, 59), tzinfo=timezone(timedelta(hours=8))
            ).astimezone(timezone.utc)
        except ValueError:
            raise SystemExit("到期日期格式应为 YYYY-MM-DD")
        if expire_dt <= now:
            raise SystemExit("到期日期必须晚于当前时间")
        expires_at = expire_dt.isoformat()
        duration_days = max(1, (expire_date - now.date()).days)
    price_per_asset = float(preset.get("price_per_asset") or 0)
    price = round(max_assets * price_per_asset, 2)
    price_text = "免费" if price <= 0 else f"{price:g} 元"
    payload = {
        "version": 1,
        "licensee": args.licensee.strip(),
        "machine_id": machine_id,
        "max_assets": max_assets,
        "max_nodes": max_nodes,
        "features": features,
        "issued_at": now.isoformat(),
        "expires_at": expires_at,
        "price": price,
        "price_text": price_text,
        "duration_days": duration_days,
        "edition": args.edition.strip() or "opensource",
        "product_version": PRODUCT_VERSION,
        "issued_by": "智能运维服务平台授权签发平台",
    }
    private = serialization.load_pem_private_key(Path(args.private_key).read_bytes(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise SystemExit("私钥不是 Ed25519 格式")
    payload_bytes = canonical(payload)
    signature = private.sign(payload_bytes)
    print(f"{b64encode(payload_bytes)}.{b64encode(signature)}")


if __name__ == "__main__":
    main()
