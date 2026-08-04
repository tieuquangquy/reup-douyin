"""Build versioned suggestion-only translations for residual review gaps."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class ResidualTranslationSuggestionError(RuntimeError):
    pass


_SUGGESTIONS: dict[str, tuple[str, str]] = {
    "下入去皮番茄": ("下入去皮番茄", "Cho cà chua đã bóc vỏ vào"),
    "大火收汁到汤汁浓稠": ("大火收汁到汤汁浓稠", "Đun lửa lớn đến khi sốt sánh lại"),
    "蔬菜": ("蔬菜", "Rau củ"),
    "热量": ("热量", "Năng lượng"),
    "请将目": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "连热": ("总热量", "Tổng năng lượng"),
    "月14": ("6月14日", "Ngày 14 tháng 6"),
    "请将管": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "保存": ("保存", "Lưu"),
    "称重值101": ("称重值101", "Giá trị cân: 101"),
    "可A": ("可食部", "Phần ăn được"),
    "凹复制记录": ("复制记录", "Sao chép bản ghi"),
    "食饮料": ("零食饮料", "Đồ ăn vặt, thức uống"),
    "回复制记17650元": ("复制记录", "Sao chép bản ghi"),
    "已购2卡86.0克": ("已购", "Đã mua"),
    "我的上传89年106.0克": ("我的上传", "Nội dung tôi tải lên"),
    "205千卡/263": ("205千卡/253克", "205 kcal/253 g"),
    "零食饮料": ("零食饮料", "Đồ ăn vặt, thức uống"),
    "日餐": ("早餐", "Bữa sáng"),
    "中式减脂人": ("中式减脂餐", "Món giảm cân kiểu Trung"),
}

_FALSE_POSITIVE_CANDIDATES = {
    "Xac nhan them性50",
    "8 kcal106.0 g年B6.0",
    "120 kcal/86.00 g饮次料",
}

_SUGGESTIONS_V22_9: dict[str, tuple[str, str]] = {
    "大火收汁到汤汁浓稠": ("大火收汁到汤汁浓稠", "Đun lửa lớn đến khi sốt sánh lại"),
    "请将目": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "连热": ("总热量", "Tổng năng lượng"),
    "月14": ("6月14日", "Ngày 14 tháng 6"),
    "请将管": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "请将食": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "重值101": ("称重值101", "Giá trị cân: 101"),
    "94/393鸡丰F/760克": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "Xac nhanthem生/5.00升": (
        "花生油 45千卡/5.00克",
        "Dầu đậu phộng 45 kcal/5.00 g",
    ),
    "89kcal/106.00g鸡/76D0克": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "Sut内奶": ("肉蛋奶", "Thịt, trứng, sữa"),
    "复制记录2八/0": ("复制记录", "Sao chép bản ghi"),
    "Rauciqgua年0": ("鸡蛋 120千卡/86.00克", "Trứng 120 kcal/86.00 g"),
    "Daluru鸡干卡/86.00克": (
        "鸡蛋 120千卡/86.00克",
        "Trứng 120 kcal/86.00 g",
    ),
    "Sao chép ban ghi *料": ("零食饮料", "Đồ ăn vặt, thức uống"),
    "凹复制记录": ("复制记录", "Sao chép bản ghi"),
    "Phan an durgg脑肉": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "Sao chép ban gh饮料": ("零食饮料", "Đồ ăn vặt, thức uống"),
    "口复制记录": ("复制记录", "Sao chép bản ghi"),
    "Phan an durog a肉": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "a tai len  土豆": ("土豆", "Khoai tây"),
    "Pho bien 零食饮料": ("零食饮料", "Đồ ăn vặt, thức uống"),
    "自定义 SuatanFA06.0k": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
    "里：": ("净含量：150克", "Khối lượng tịnh: 150 g"),
}

_SUGGESTIONS_V22_11_1: dict[str, tuple[str, str]] = {
    "素炒青菜": ("素炒青菜", "Rau xanh xào"),
    "大火收汗到汤汁浓稠": (
        "大火收汁到汤汁浓稠",
        "Đun lửa lớn đến khi nước sốt sánh lại",
    ),
    "请将售": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "89 kcal/106.00g F/5.0套升": (
        "花生油 45千卡/5.00毫升",
        "Dầu đậu phộng 45 kcal/5.00 ml",
    ),
    "早食": ("早餐", "Bữa sáng"),
    "Phan in dugg胸肉 176.0克": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "堂n Da luru": ("常见", "Phổ biến"),
    "Tuy chinh286.0克": (
        "馒头 192千卡/86.00克",
        "Bánh màn thầu 192 kcal/86.00 g",
    ),
    "120 kcal/86.00 g 29干106.": (
        "豆腐 89千卡/106.00克",
        "Đậu phụ 89 kcal/106.00 g",
    ),
    "复制记录": ("复制记录", "Sao chép bản ghi"),
    "食Duiga": ("食谱", "Công thức"),
    "36 kcal/112.00 g鸡腿": (
        "鸡腿 36千卡/112.00克",
        "Đùi gà 36 kcal/112.00 g",
    ),
    "里：": ("净含量：150克", "Khối lượng tịnh: 150 g"),
}

_SUGGESTIONS_V22_13_1: dict[str, tuple[str, str]] = {
    "请将": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "814日": ("6月14日", "Ngày 14 tháng 6"),
    "请将食": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "即热米饭0克": ("即热米饭", "Cơm ăn liền"),
}

_SUGGESTIONS_V22_14_1: dict[str, tuple[str, str]] = {
    "4A00克": (
        "即热米饭 286千卡/170.00克",
        "Cơm ăn liền 286 kcal/170.00 g",
    ),
    "Damua86.0克": (
        "馒头 192千卡/86.00克",
        "Bánh màn thầu 192 kcal/86.00 g",
    ),
}

_SUGGESTIONS_V22_15_1: dict[str, tuple[str, str]] = {
    "Hoan thanh205千卡/2": (
        "土豆 205千卡/253.00克",
        "Khoai tây 205 kcal/253.00 g",
    ),
}

_SUGGESTIONS_V22_16_1: dict[str, tuple[str, str]] = {
    "一在秤上": ("在秤上", "Trên cân"),
    "在上": ("在秤上", "Trên cân"),
    "秤上": ("在秤上", "Trên cân"),
    "科上": ("在秤上", "Trên cân"),
    "月00克": ("170.00克", "170.00 g"),
    "Phan anduoc/.0升": (
        "花生油 45千卡/5.00毫升",
        "Dầu đậu phộng 45 kcal/5.00 ml",
    ),
    "Noidung toitilen干卡/06": (
        "豆腐 89千卡/106.00克",
        "Đậu phụ 89 kcal/106.00 g",
    ),
    "定义Suatan120干F/B6.00克": (
        "鸡蛋 120千卡/86.00克",
        "Trứng 120 kcal/86.00 g",
    ),
    "2. Nhanh豆腐96.0克": (
        "豆腐 89千卡/106.00克",
        "Đậu phụ 89 kcal/106.00 g",
    ),
}

_SUGGESTIONS_V22_17_1: dict[str, tuple[str, str]] = {
    "定义Suatan120干=/8.00克": (
        "鸡蛋 120千卡/86.00克",
        "Trứng 120 kcal/86.00 g",
    ),
}

_SUGGESTIONS_V22_18_1: dict[str, tuple[str, str]] = {
    "在秤上": ("在秤上", "Trên cân"),
    "Xacnhndthem/5.0升": (
        "花生油 45千卡/5.00毫升",
        "Dầu đậu phộng 45 kcal/5.00 ml",
    ),
    "192 kcal/86.00g干00": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
}

_SUGGESTIONS_V22_20_1: dict[str, tuple[str, str]] = {
    "Xac nhan them脑肉 n76.00x": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "Cong thuRC干卡/860克": (
        "馒头 192千卡/86.00克",
        "Bánh màn thầu 192 kcal/86.00 g",
    ),
}

_SUGGESTIONS_V22_21_1: dict[str, tuple[str, str]] = {
    "蛋白么": ("蛋白质（克）", "Chất đạm (g)"),
    "Tuy chinh鸡胸肉E7e.0克": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "BatailenB年手e": (
        "豆腐 89千卡/106.00克",
        "Đậu phụ 89 kcal/106.00 g",
    ),
    "Hoanthanh205千卡26": (
        "土豆 205千卡/253.00克",
        "Khoai tây 205 kcal/253.00 g",
    ),
}

_SUGGESTIONS_V22_22_1: dict[str, tuple[str, str]] = {
    "软重信": ("称重值", "Giá trị cân"),
    "通荷健序": ("薄荷健康", "Boohee Health"),
}

_SUGGESTIONS_V22_23_1: dict[str, tuple[str, str]] = {
    "测量中": ("测量中", "Đang đo"),
    "你重值10": ("称重值101", "Giá trị cân: 101"),
    "在秤": ("在秤上", "Trên cân"),
}

_V22_9_FALSE_POSITIVE_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_e80cbc078a98": (
        "蔬菜就搭配一份",
        "Rau củ ăn kèm một phần",
    ),
    "outres_df5f018f33e0": ("蛋白质（克）", "Chất đạm (g)"),
    "outres_c60ca50c9bfb": ("脂肪（克）", "Chất béo (g)"),
    "outres_fad072e39463": ("用餐时间", "Giờ ăn"),
    "outres_27619ae7167b": (
        "馒头 192千卡/86.00克",
        "Bánh màn thầu 192 kcal/86.00 g",
    ),
    "outres_cc3a5f20da91": (
        "豆腐 89千卡/106.00克",
        "Đậu phụ 89 kcal/106.00 g",
    ),
    "outres_ac86e1a51ed5": (
        "土豆 205千卡/253.00克",
        "Khoai tây 205 kcal/253.00 g",
    ),
    "outres_c4ee9265e31d": ("自定义", "Tùy chỉnh"),
    "outres_fa7595c20903": ("薄荷健康", "Boohee Health"),
}

_V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_9fbcc452ac31": ("请选择食物", "Vui lòng chọn thực phẩm"),
    "outres_9cb4edc50708": ("碳水（克）", "Tinh bột (g)"),
    "outres_92edf5a5592c": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
    "outres_53b5e601e815": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
    "outres_76737b7111c6": (
        "净含量：150克",
        "Khối lượng tịnh: 150 g",
    ),
    "outres_d91f0b1291ad": (
        "净含量：150克",
        "Khối lượng tịnh: 150 g",
    ),
}

_V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_4a9daff7d28d": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
    "outres_c3d767aba26a": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
}

_V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_8c8db2e14465": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
}

_V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_098a5e8ef150": (
        "虾 99千卡/106.00克",
        "Tôm 99 kcal/106.00 g",
    ),
}

_V22_16_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_c2e4234020f2": ("可食部", "Phần ăn được"),
    "outres_9d9bd55044fa": ("170.00克", "170.00 g"),
}

_V22_17_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_a634a0ee5fc3": ("鹰嘴豆(干)", "Đậu gà (khô)"),
}

_V22_18_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_063238148f79": ("千卡/千焦", "kcal/kJ"),
    "outres_eb6f3266292a": (
        "花生油 45千卡/5.00毫升",
        "Dầu đậu phộng 45 kcal/5.00 ml",
    ),
    "outres_651a45e6eba8": (
        "鸡蛋 120千卡/86.00克",
        "Trứng 120 kcal/86.00 g",
    ),
}

_V22_20_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_a6f4cc53915a": ("脂肪（克）", "Chất béo (g)"),
}

_V22_22_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_4302d8ed38fd": ("可食部", "Phần ăn được"),
    "outres_3116ec6c0e7d": ("脂肪（克）", "Chất béo (g)"),
}

_V22_23_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_8c4f4c7126cd": ("用餐时间", "Giờ ăn"),
    "outres_a603ae9c7ca2": ("全部可食", "Ăn được toàn bộ"),
}

_V22_24_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_e3c30c811a45": ("用餐时间", "Giờ ăn"),
    "outres_5d22f4ca5ef3": ("称重值101", "Giá trị cân: 101"),
}

_V22_25_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_9e802017e3f2": (
        "豆腐 89千卡/106.00克",
        "Đậu phụ 89 kcal/106.00 g",
    ),
}

_V22_26_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_976a35112da5": ("脂肪（克）", "Chất béo (g)"),
    "outres_268050156929": (
        "土豆 205千卡/253.00克",
        "Khoai tây 205 kcal/253.00 g",
    ),
}

_V22_28_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_7e8c4bddf4aa": ("称重值", "Giá trị cân"),
    "outres_d90de50a2ba3": ("可食部", "Phần ăn được"),
}

_V22_29_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_8f8d67f265f8": ("用餐时间", "Giờ ăn"),
    "outres_977da0505e39": ("用餐时间", "Giờ ăn"),
}

_V22_31_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_3d16c1a5a9a7": ("称重值", "Trọng lượng"),
    "outres_60e4bf7e72fc": ("用餐时间", "Giờ ăn"),
}

_V22_37_2_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # Both crops show the same approved source label.  Local OCR read the
    # first occurrence as 可低部 and only the final component at frame 610.
    "outres_c93580143e22": ("可食部", "Phần ăn được"),
    "outres_2617b1c82d4a": ("可食部", "Phần ăn được"),
}

_V22_39_2_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_0903eb59a58d": ("用餐时间", "Giờ ăn"),
    "outres_602a906b47d8": ("脂肪（克）", "Chất béo (g)"),
    "outres_ce3b6e35bba3": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "outres_16113eb3cab5": (
        "鸡腿 343千卡/235.00克",
        "Đùi gà 343 kcal/235.00 g",
    ),
    "outres_51cd2d0a203c": (
        "贝贝南瓜 197千卡/263.00克",
        "Bí đỏ Beibei 197 kcal/263.00 g",
    ),
}

_V22_40_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    "outres_feefb20b4e8b": (
        "贝贝南瓜 197千卡/263.00克",
        "Bí đỏ Beibei 197 kcal/263.00 g",
    ),
    "outres_51cd2d0a203c": (
        "贝贝南瓜 197千卡/263.00克",
        "Bí đỏ Beibei 197 kcal/263.00 g",
    ),
}

_V22_42_2_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # The V22.39 source-boundary attempt for this approved row failed closed.
    # The later residual combines rendered Vietnamese with a truncated source
    # metric, but the contact sheet and Phase-2 authority still identify the
    # same chicken-leg row unambiguously.
    "outres_f28122ca48a6": (
        "鸡腿 343千卡/235.00克",
        "Đùi gà 343 kcal/235.00 g",
    ),
}

_V22_43_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # Output OCR merged the already-rendered "Tùy chỉnh" label with a
    # truncated chicken-breast source row. Phase-2 and the effective render
    # contract agree on the complete operator-approved row below.
    "outres_6b265e1c7185": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
}

_V22_44_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # Output OCR fused Vietnamese overlays with truncated source UI rows.
    # The contact sheets retain enough source evidence to bind these rows to
    # their existing Phase-2 translation authorities. In particular, the
    # frame-648 nearest match of "0 g" is rejected as a partial OCR artifact.
    "outres_ea75ce572045": (
        "花生油 45千卡/5.00毫升",
        "Dầu đậu phộng 45 kcal/5.00 ml",
    ),
    "outres_50a7f3e47acd": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
    "outres_7d6c805d76d6": (
        "鸡胸肉 208千卡/176.00克",
        "Ức gà 208 kcal/176.00 g",
    ),
}

_V22_45_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # OCR fused the already-rendered upload label with the approved mantou
    # source row. Reuse the exact Phase-2 authority rather than translating
    # the mixed output string.
    "outres_22b8fd370a00": (
        "馒头 192千卡/86.00克",
        "Bánh màn thầu 192 kcal/86.00 g",
    ),
}

_V22_46_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # The residual contains only the unit/value fragment, while its evidence
    # crop shows the operator-approved potato row in the same source geometry.
    "outres_eb01b86940a4": (
        "土豆 205千卡/253.00克",
        "Khoai tây 205 kcal/253.00 g",
    ),
}

_V22_48_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # The dense-panel rerender left a confirmed zero-gram source fragment at
    # the panel's right edge. Keep the numeric value and normalize the unit.
    "outres_d3ec1617c72f": ("0克", "0 g"),
}

_V22_49_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # The panel-edge residual "00克" is the visible suffix of the approved
    # potato row in the source frame, not an independent zero-gram label.
    "outres_d3ec1617c72f": (
        "土豆 205千卡/253.00克",
        "Khoai tây 205 kcal/253.00 g",
    ),
}

_V22_50_1_RECLASSIFICATIONS: dict[str, tuple[str, str]] = {
    # OCR lost the leading glyph of the bottom-edge meal label. The source
    # evidence shows 早餐; reuse the project's approved Vietnamese label.
    "outres_d44d72c08aea": ("早餐", "Bữa sáng"),
}


def reclassification_for_cluster(
    cluster_id: str,
    *,
    suggestion_version: str,
) -> tuple[str, str] | None:
    version = str(suggestion_version or "").strip().upper()
    if version == "V22_50_1":
        return _V22_50_1_RECLASSIFICATIONS.get(str(cluster_id)) or reclassification_for_cluster(
            cluster_id, suggestion_version="V22_49_1"
        )
    if version == "V22_49_1":
        return _V22_49_1_RECLASSIFICATIONS.get(str(cluster_id)) or reclassification_for_cluster(
            cluster_id, suggestion_version="V22_48_1"
        )
    if version == "V22_48_1":
        return _V22_48_1_RECLASSIFICATIONS.get(str(cluster_id)) or reclassification_for_cluster(
            cluster_id, suggestion_version="V22_46_1"
        )
    if version == "V22_37_2":
        return _V22_37_2_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_31_1",
        )
    if version == "V22_39_2":
        return _V22_39_2_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_37_2",
        )
    if version == "V22_40_1":
        return _V22_40_1_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_39_2",
        )
    if version == "V22_42_2":
        return _V22_42_2_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_40_1",
        )
    if version == "V22_43_1":
        return _V22_43_1_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_42_2",
        )
    if version == "V22_44_1":
        return _V22_44_1_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_43_1",
        )
    if version == "V22_45_1":
        return _V22_45_1_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_44_1",
        )
    if version == "V22_46_1":
        return _V22_46_1_RECLASSIFICATIONS.get(
            str(cluster_id)
        ) or reclassification_for_cluster(
            cluster_id,
            suggestion_version="V22_45_1",
        )
    if version == "V22_9":
        return _V22_9_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
    if version == "V22_11_1":
        return _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
    if version == "V22_13_1":
        return _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
    if version == "V22_14_1":
        return (
            _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_15_1":
        return (
            _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_16_1":
        return (
            _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_17_1":
        return (
            _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_18_1":
        return (
            _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_20_1":
        return (
            _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_21_1":
        return (
            _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_22_1":
        return (
            _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_23_1":
        return (
            _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_24_1":
        return (
            _V22_24_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_25_1":
        return (
            _V22_25_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_24_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version in {"V22_26_1", "V22_27_1"}:
        return (
            _V22_26_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_25_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_24_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_28_1":
        return (
            _V22_28_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_26_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_25_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_24_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_29_1":
        return (
            _V22_29_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_28_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_26_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_25_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_24_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    if version == "V22_31_1":
        return (
            _V22_31_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_29_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_28_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_26_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_25_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_24_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_23_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_22_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_20_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_18_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_17_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_16_1_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_15_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_14_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_13_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
            or _V22_11_1_FALSE_POSITIVE_RECLASSIFICATIONS.get(str(cluster_id))
        )
    return None


def suggestion_for_text(
    value: str,
    *,
    suggestion_version: str = "V22_8_1",
) -> dict[str, Any] | None:
    observed = str(value or "").strip()
    if observed in _FALSE_POSITIVE_CANDIDATES:
        return {
            "suggestion_status": "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE",
            "source_text_observed": observed,
            "source_text_corrected": None,
            "vi_text_suggested": None,
        }
    version = str(suggestion_version or "").strip().upper()
    if version == "V22_9":
        suggestion = _SUGGESTIONS_V22_9.get(observed)
    elif version == "V22_11_1":
        suggestion = _SUGGESTIONS_V22_11_1.get(observed) or _SUGGESTIONS.get(
            observed
        )
    elif version == "V22_13_1":
        suggestion = (
            _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_14_1":
        suggestion = (
            _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_15_1":
        suggestion = (
            _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_16_1":
        suggestion = (
            _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_17_1":
        suggestion = (
            _SUGGESTIONS_V22_17_1.get(observed)
            or _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_18_1":
        suggestion = (
            _SUGGESTIONS_V22_18_1.get(observed)
            or _SUGGESTIONS_V22_17_1.get(observed)
            or _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_20_1":
        suggestion = (
            _SUGGESTIONS_V22_20_1.get(observed)
            or _SUGGESTIONS_V22_18_1.get(observed)
            or _SUGGESTIONS_V22_17_1.get(observed)
            or _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_21_1":
        suggestion = (
            _SUGGESTIONS_V22_21_1.get(observed)
            or _SUGGESTIONS_V22_20_1.get(observed)
            or _SUGGESTIONS_V22_18_1.get(observed)
            or _SUGGESTIONS_V22_17_1.get(observed)
            or _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version == "V22_22_1":
        suggestion = (
            _SUGGESTIONS_V22_22_1.get(observed)
            or _SUGGESTIONS_V22_21_1.get(observed)
            or _SUGGESTIONS_V22_20_1.get(observed)
            or _SUGGESTIONS_V22_18_1.get(observed)
            or _SUGGESTIONS_V22_17_1.get(observed)
            or _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    elif version in {
        "V22_23_1",
        "V22_24_1",
        "V22_25_1",
        "V22_26_1",
        "V22_27_1",
        "V22_28_1",
        "V22_29_1",
        "V22_31_1",
        "V22_37_2",
        "V22_39_2",
        "V22_40_1",
    }:
        suggestion = (
            _SUGGESTIONS_V22_23_1.get(observed)
            or _SUGGESTIONS_V22_22_1.get(observed)
            or _SUGGESTIONS_V22_21_1.get(observed)
            or _SUGGESTIONS_V22_20_1.get(observed)
            or _SUGGESTIONS_V22_18_1.get(observed)
            or _SUGGESTIONS_V22_17_1.get(observed)
            or _SUGGESTIONS_V22_16_1.get(observed)
            or _SUGGESTIONS_V22_15_1.get(observed)
            or _SUGGESTIONS_V22_14_1.get(observed)
            or _SUGGESTIONS_V22_13_1.get(observed)
            or _SUGGESTIONS_V22_11_1.get(observed)
            or _SUGGESTIONS.get(observed)
        )
    else:
        suggestion = _SUGGESTIONS.get(observed)
    if suggestion is None:
        return None
    source, vi_text = suggestion
    return {
        "suggestion_status": "TRANSLATION_SUGGESTION_ONLY",
        "source_text_observed": observed,
        "source_text_corrected": source,
        "vi_text_suggested": vi_text,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ResidualTranslationSuggestionError(f"{path.name} must contain an object")
    return payload


def build_suggestions(
    run_root: str | Path,
    *,
    review_name: str = "phase4_output_residual_review_v22_8.json",
    approval_name: str = "phase4_output_residual_review_approval_v22_8.json",
    suggestion_version: str = "V22_8_1",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    for value in (review_name, approval_name):
        if Path(str(value)).name != str(value) or not str(value).endswith(".json"):
            raise ResidualTranslationSuggestionError("Invalid authority filename")
    review_path = root / review_name
    approval_path = root / approval_name
    review = _load_object(review_path)
    approval = _load_object(approval_path)
    review_unsigned = dict(review)
    review_hash = str(review_unsigned.pop("review_sha256", "") or "")
    approval_unsigned = dict(approval)
    approval_hash = str(approval_unsigned.pop("approval_sha256", "") or "")
    if (
        review_hash != _sha256_json(review_unsigned)
        or approval_hash != _sha256_json(approval_unsigned)
        or
        str(approval.get("status") or "")
        != "PHASE4_OUTPUT_RESIDUAL_REVIEW_APPROVED"
        or str(dict(approval.get("review_ref") or {}).get("sha256") or "")
        != _sha256_file(review_path)
        or str(dict(approval.get("review_ref") or {}).get("review_sha256") or "")
        != review_hash
    ):
        raise ResidualTranslationSuggestionError("Residual review approval is stale")
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    def phase3_near_match(case_root: Path, observed: str) -> tuple[str, str] | None:
        timeline_path = case_root / "phase3_translation_timeline.json"
        if not timeline_path.is_file():
            return None
        try:
            timeline = _load_object(timeline_path)
        except ResidualTranslationSuggestionError:
            return None
        def norm(value: str) -> str:
            return str(value or "").replace("減", "减").replace(" ", "")
        observed_norm = norm(observed)
        best: tuple[float, str, str] | None = None
        for raw in list(timeline.get("content_objects") or []):
            row = dict(raw)
            if str(row.get("review_status") or "") != "TRANSLATION_APPROVED":
                continue
            source = str(row.get("zh_approved") or "").strip()
            vi = str(row.get("vi_text_approved") or "").strip()
            if not source or not vi:
                continue
            score = difflib.SequenceMatcher(None, observed_norm, norm(source)).ratio()
            if best is None or score > best[0]:
                best = (score, source, vi)
        return (best[1], best[2]) if best is not None and best[0] >= 0.40 else None
    for case in list(review.get("cases") or []):
        case_id = str(dict(case).get("case_id") or "")
        for cluster in list(dict(case).get("clusters") or []):
            item = dict(cluster)
            recommendation = dict(item.get("recommendation") or {})
            category = str(recommendation.get("decision") or "")
            cluster_id = str(item.get("cluster_id") or "")
            reclassification = reclassification_for_cluster(
                cluster_id,
                suggestion_version=suggestion_version,
            )
            if (
                category != "TRANSLATION_INPUT_AND_COVERAGE_REVIEW"
                and reclassification is None
            ):
                continue
            observed = str(recommendation.get("source_text_suggested") or "")
            evidence = dict(item.get("evidence") or {})
            active_intersections = list(recommendation.get("active_intersections") or [])
            crop_delta = float(evidence.get("source_render_crop_mean_abs_delta") or 0.0)
            detections = list(item.get("detections") or [])
            geometry = dict(dict(detections[0]).get("geometry") or {}) if detections else {}
            glyph_area = float(geometry.get("width") or 0.0) * float(geometry.get("height") or 0.0)
            # A confirmed glyph with no active editor/content intersection and a
            # near-identical source/render crop is source-intrinsic (often phone
            # UI or texture), not an untranslated overlay.  Route it through the
            # auditable false-positive path instead of inventing translation text.
            if (
                category == "TRANSLATION_INPUT_AND_COVERAGE_REVIEW"
                and not active_intersections
                and 0.0 < crop_delta <= 4.0
            ):
                suggestion = {
                    "suggestion_status": "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE",
                    "source_text_observed": observed,
                    "vi_text_suggested": None,
                    "review_decision_overridden": "SOURCE_INTRINSIC_BOUNDING_EVIDENCE",
                }
            elif (
                category == "TRANSLATION_INPUT_AND_COVERAGE_REVIEW"
                and glyph_area > 0.0
                and glyph_area <= 0.001
                and crop_delta <= 6.0
            ):
                # Numeric/unit-sized glyphs inside an intrinsic UI are not a
                # safe basis for translation or an extra cover rectangle.
                suggestion = {
                    "suggestion_status": "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE",
                    "source_text_observed": observed,
                    "vi_text_suggested": None,
                    "review_decision_overridden": "SOURCE_INTRINSIC_SMALL_GLYPH_EVIDENCE",
                }
            else:
                suggestion = (
                    {
                        "suggestion_status": "TRANSLATION_SUGGESTION_ONLY",
                        "source_text_observed": observed,
                        "source_text_corrected": reclassification[0],
                        "vi_text_suggested": reclassification[1],
                        "review_decision_overridden": category,
                    }
                    if reclassification is not None
                    else suggestion_for_text(
                        observed, suggestion_version=suggestion_version
                    )
                )
            if suggestion is None:
                near = phase3_near_match(root / case_id, observed)
                if near is not None:
                    suggestion = {
                        "suggestion_status": "PHASE3_APPROVED_NEAR_MATCH",
                        "source_text_observed": observed,
                        "source_text_corrected": near[0],
                        "vi_text_suggested": near[1],
                        "translation_authority": "EXISTING_PHASE3_APPROVAL_NEAR_MATCH",
                    }
            base = {
                "case_id": case_id,
                "cluster_id": item.get("cluster_id"),
                "representative_frame_index": item.get("representative_frame_index"),
                "evidence_ref": dict(item.get("evidence") or {}).get(
                    "source_render_contact_sheet"
                ),
            }
            if suggestion is None:
                unresolved.append({**base, "source_text_observed": observed})
            else:
                rows.append({**base, **suggestion})
    payload: dict[str, Any] = {
        "schema_version": "phase4_output_residual_translation_suggestions_v1",
        "suggestion_version": str(suggestion_version).strip().upper(),
        "status": (
            "SUGGESTIONS_READY_FOR_OPERATOR_REVIEW"
            if not unresolved
            else "OPERATOR_TRANSLATION_INPUT_REQUIRED"
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_approval_written": False,
        "authority_refs": {
            "review": {
                "path": review_path.name,
                "sha256": _sha256_file(review_path),
                "review_sha256": review.get("review_sha256"),
            },
            "review_approval": {
                "path": approval_path.name,
                "sha256": _sha256_file(approval_path),
                "approval_sha256": approval.get("approval_sha256"),
            },
        },
        "counts": {
            "suggestions": len(rows),
            "translation_suggestions": sum(
                row["suggestion_status"] == "TRANSLATION_SUGGESTION_ONLY"
                for row in rows
            ),
            "false_positive_candidates": sum(
                row["suggestion_status"]
                == "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE"
                for row in rows
            ),
            "unresolved": len(unresolved),
        },
        "suggestions": rows,
        "unresolved": unresolved,
        "non_goals": [
            "do_not_write_translation_approval",
            "do_not_write_false_positive_approval",
            "do_not_write_remediation_authority",
        ],
    }
    token_seed = _sha256_json(payload)[:12].upper()
    payload["operator_approval_token"] = (
        "PHASE4_OUTPUT_RESIDUAL_TRANSLATION_SUGGESTIONS_APPROVED_"
        f"{str(suggestion_version).strip().upper()}_{token_seed}"
    )
    payload["suggestions_sha256"] = _sha256_json(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_output_residual_translation_suggestions"
    )
    parser.add_argument("run_root")
    parser.add_argument(
        "--review-name", default="phase4_output_residual_review_v22_8.json"
    )
    parser.add_argument(
        "--approval-name",
        default="phase4_output_residual_review_approval_v22_8.json",
    )
    parser.add_argument("--suggestion-version", default="V22_8_1")
    parser.add_argument(
        "--output-name",
        default="phase4_output_residual_translation_suggestions_v22_8_1.json",
    )
    args = parser.parse_args()
    try:
        root = Path(args.run_root).resolve()
        payload = build_suggestions(
            root,
            review_name=args.review_name,
            approval_name=args.approval_name,
            suggestion_version=args.suggestion_version,
        )
        output_name = str(args.output_name or "").strip()
        if Path(output_name).name != output_name or not output_name.endswith(".json"):
            raise ResidualTranslationSuggestionError("Invalid output filename")
        path = root / output_name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)
    except (OSError, ValueError, json.JSONDecodeError, ResidualTranslationSuggestionError) as exc:
        print(f"[PHASE4-OUTPUT-RESIDUAL-TRANSLATION][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "counts": payload["counts"],
                "operator_approval_token": payload["operator_approval_token"],
                "suggestions_sha256": payload["suggestions_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
