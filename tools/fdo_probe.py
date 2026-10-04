"""FDO 设备安全上船协议最小探针（卷102 W102-01 · BSD-3 可参考，Python 独立实现）。

模拟 FIDO Device Onboard 核心流程状态机（不实现密码学，退化路径显式标注）：
DI（出厂初始化生成所有权凭证）→ TO1（rendezvous 发现所有者）→ TO2（所有权转移 + 签发凭证）。

源结构对照（fido-device-onboard-rs）：
- OwnershipVoucher：data-formats/src/ownershipvoucher.rs:37（版本/头部/设备证书链/条目）
- TO1：data-formats/src/messages/v11/to1.rs:12 HelloRV（rendezvous 握手）
- TO2：data-formats/src/messages/v11/to2.rs:19 HelloDevice → :478 Done（所有权转移全流程）
本探针是纯 Python 协议流程骨架，供台账身份层对照，不实现任何密码学运算。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FdoStage(str, Enum):
    """协议阶段状态机。"""
    MANUFACTURED = "manufactured"    # 出厂：预置密钥与设备身份
    INITIALIZED = "initialized"      # DI 完成：已生成所有权凭证
    RENDEZVOUS = "rendezvous"        # TO1：已发现所有者
    TRANSFERRING = "transferring"    # TO2：所有权转移进行中
    ONBOARDED = "onboarded"          # 凭证签发完成，可入台账
    FAILED = "failed"


@dataclass
class DeviceCredential:
    """出厂预置设备身份（对照 DeviceCredential：设备唯一 ID + 密钥引用）。"""
    device_id: str
    public_key_ref: str


@dataclass
class OwnershipVoucher:
    """所有权凭证（对照 ownershipvoucher.rs:37 的条目化结构，密码学字段退化）。"""
    serial: str
    device_id: str
    owner_public_key_ref: str
    entries: list[str] = field(default_factory=list)

    def add_entry(self, entry: str) -> None:
        self.entries.append(entry)


class FdoOnboarding:
    """FDO 流程状态机：出厂 → DI → TO1 → TO2 → 上船完成。"""

    def __init__(self, device_id: str):
        self.device = DeviceCredential(device_id=device_id, public_key_ref=f"key:{device_id}")
        self.voucher: OwnershipVoucher | None = None
        self.stage = FdoStage.MANUFACTURED
        self.issued_credential_ref: str | None = None

    def device_initialize(self) -> OwnershipVoucher:
        """DI：生成所有权凭证（绑定设备 ID，等待所有者接管）。重复初始化拒绝。"""
        if self.stage is not FdoStage.MANUFACTURED:
            raise RuntimeError(f"DI 只允许从出厂态发起，当前 {self.stage.value}")
        self.voucher = OwnershipVoucher(
            serial=f"OV-{self.device.device_id}",
            device_id=self.device.device_id,
            owner_public_key_ref="",
        )
        self.stage = FdoStage.INITIALIZED
        return self.voucher

    def rendezvous(self, owner_public_key_ref: str) -> bool:
        """TO1：rendezvous 发现所有者；空引用视为无主可接，返回 False。"""
        if self.stage is not FdoStage.INITIALIZED:
            raise RuntimeError(f"TO1 需处于已初始化态，当前 {self.stage.value}")
        if not owner_public_key_ref:
            return False
        self.stage = FdoStage.RENDEZVOUS
        return True

    def transfer_ownership(self, owner_public_key_ref: str) -> None:
        """TO2：所有权转移。同主重入幂等；凭证已绑定他主时拒绝（防重放/抢注退化近似）。"""
        if self.stage not in (FdoStage.RENDEZVOUS, FdoStage.TRANSFERRING, FdoStage.ONBOARDED):
            raise RuntimeError(f"TO2 需先完成 TO1，当前 {self.stage.value}")
        if self.voucher is None:
            raise RuntimeError("缺少所有权凭证")
        self.stage = FdoStage.TRANSFERRING
        if self.voucher.owner_public_key_ref and self.voucher.owner_public_key_ref != owner_public_key_ref:
            self.stage = FdoStage.FAILED
            raise ValueError("所有权凭证已绑定其他所有者")
        self.voucher.owner_public_key_ref = owner_public_key_ref
        self.voucher.add_entry(f"owner:{owner_public_key_ref}")
        # 凭证签发（退化）：以确定性引用替代密码学凭证
        self.issued_credential_ref = f"cred:{self.device.device_id}:{owner_public_key_ref}"
        self.stage = FdoStage.ONBOARDED

    def verify_credential(self, credential_ref: str) -> bool:
        """凭证验证：仅接受本机签发路径的引用（无密码学的退化验证）。"""
        return self.stage is FdoStage.ONBOARDED and credential_ref == self.issued_credential_ref

    def summary(self) -> dict:
        return {
            "device_id": self.device.device_id,
            "stage": self.stage.value,
            "voucher_serial": self.voucher.serial if self.voucher else None,
            "credential_ref": self.issued_credential_ref,
        }