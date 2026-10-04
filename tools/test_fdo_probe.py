"""fdo_probe 验收硬线（卷102 W102-01）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fdo_probe import FdoOnboarding, FdoStage  # noqa: E402


def test_di_and_rendezvous():
    """DI 生成凭证 + TO1 接受所有者；重复 DI 被拒。"""
    fdo = FdoOnboarding("dev-001")
    assert fdo.stage is FdoStage.MANUFACTURED
    voucher = fdo.device_initialize()
    assert voucher.serial == "OV-dev-001" and voucher.device_id == "dev-001"
    assert fdo.stage is FdoStage.INITIALIZED
    with pytest.raises(RuntimeError):
        fdo.device_initialize()
    assert fdo.rendezvous("") is False  # 空所有者拒绝，仍处初始化态
    assert fdo.rendezvous("owner-A") is True
    assert fdo.stage is FdoStage.RENDEZVOUS
    with pytest.raises(RuntimeError):
        fdo.rendezvous("owner-B")  # 已过 TO1，重复 rendezvous 非法


def test_transfer_and_verify():
    """TO2 所有权转移 + 凭证签发/验证闭环。"""
    fdo = FdoOnboarding("dev-002")
    fdo.device_initialize()
    fdo.rendezvous("owner-A")
    fdo.transfer_ownership("owner-A")
    assert fdo.stage is FdoStage.ONBOARDED
    cred = fdo.issued_credential_ref
    assert cred and fdo.verify_credential(cred) is True
    assert fdo.verify_credential("cred:dev-002:owner-B") is False
    s = fdo.summary()
    assert s["voucher_serial"] == "OV-dev-002" and s["stage"] == "onboarded"


def test_voucher_rebind_rejected():
    """凭证已绑定 A 后，B 抢注被拒且进入 FAILED。"""
    fdo = FdoOnboarding("dev-003")
    fdo.device_initialize()
    fdo.rendezvous("owner-A")
    fdo.transfer_ownership("owner-A")
    # 同主重入幂等；已上船后再以另一所有者转移：凭证已绑定他主 → 拒绝
    fdo.transfer_ownership("owner-A")
    assert fdo.stage is FdoStage.ONBOARDED
    with pytest.raises(ValueError, match="已绑定"):
        fdo.transfer_ownership("owner-B")
    assert fdo.stage is FdoStage.FAILED
    once = FdoOnboarding("dev-004")
    once.device_initialize()
    with pytest.raises(RuntimeError):
        once.transfer_ownership("owner-A")  # 未 TO1 直接 TO2 非法