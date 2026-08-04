from scripts.build_phase4_output_residual_translation_suggestions import (
    reclassification_for_cluster,
    suggestion_for_text,
)


def test_translates_clear_food_instruction() -> None:
    result = suggestion_for_text("\u4e0b\u5165\u53bb\u76ae\u756a\u8304")

    assert result is not None
    assert result["vi_text_suggested"] == "Cho cà chua đã bóc vỏ vào"


def test_routes_mixed_render_ocr_to_false_positive_candidate() -> None:
    result = suggestion_for_text("Xac nhan them\u602750")

    assert result is not None
    assert result["suggestion_status"] == "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE"
    assert result["vi_text_suggested"] is None


def test_v22_11_corrects_mixed_peanut_oil_ocr_to_milliliters() -> None:
    result = suggestion_for_text(
        "89 kcal/106.00g F/5.0\u5957\u5347",
        suggestion_version="V22_11_1",
    )

    assert result is not None
    assert result["source_text_corrected"] == "\u82b1\u751f\u6cb9 45\u5343\u5361/5.00\u6beb\u5347"
    assert result["vi_text_suggested"] == (
        "D\u1ea7u \u0111\u1eadu ph\u1ed9ng 45 kcal/5.00 ml"
    )


def test_v22_11_corrects_tofu_value_from_source_evidence() -> None:
    result = suggestion_for_text(
        "120 kcal/86.00 g 29\u5e72106.",
        suggestion_version="V22_11_1",
    )

    assert result is not None
    assert result["source_text_corrected"] == "\u8c46\u8150 89\u5343\u5361/106.00\u514b"
    assert result["vi_text_suggested"] == "\u0110\u1eadu ph\u1ee5 89 kcal/106.00 g"


def test_v22_11_reclassifies_real_shrimp_label_from_false_positive_review() -> None:
    result = reclassification_for_cluster(
        "outres_92edf5a5592c",
        suggestion_version="V22_11_1",
    )

    assert result == (
        "\u867e 99\u5343\u5361/106.00\u514b",
        "T\u00f4m 99 kcal/106.00 g",
    )


def test_v22_13_maps_instant_rice_and_date_ocr_variants() -> None:
    instant_rice = suggestion_for_text(
        "\u5373\u70ed\u7c73\u996d0\u514b",
        suggestion_version="V22_13_1",
    )
    date = suggestion_for_text("814\u65e5", suggestion_version="V22_13_1")

    assert instant_rice["source_text_corrected"] == "\u5373\u70ed\u7c73\u996d"
    assert instant_rice["vi_text_suggested"] == "C\u01a1m \u0103n li\u1ec1n"
    assert date["source_text_corrected"] == "6\u670814\u65e5"
    assert date["vi_text_suggested"] == "Ng\u00e0y 14 th\u00e1ng 6"


def test_v22_13_reclassifies_real_shrimp_false_positive_cluster() -> None:
    result = reclassification_for_cluster(
        "outres_4a9daff7d28d",
        suggestion_version="V22_13_1",
    )

    assert result == (
        "\u867e 99\u5343\u5361/106.00\u514b",
        "T\u00f4m 99 kcal/106.00 g",
    )


def test_v22_14_inherits_prior_mapping_and_corrects_new_numeric_rows() -> None:
    inherited = suggestion_for_text(
        "\u8bf7\u5c06",
        suggestion_version="V22_14_1",
    )
    rice = suggestion_for_text("4A00\u514b", suggestion_version="V22_14_1")
    mantou = suggestion_for_text(
        "Damua86.0\u514b",
        suggestion_version="V22_14_1",
    )

    assert inherited["source_text_corrected"] == "\u8bf7\u9009\u62e9\u98df\u7269"
    assert rice["source_text_corrected"] == (
        "\u5373\u70ed\u7c73\u996d 286\u5343\u5361/170.00\u514b"
    )
    assert mantou["source_text_corrected"] == (
        "\u9992\u5934 192\u5343\u5361/86.00\u514b"
    )


def test_v22_15_inherits_prior_mapping_and_corrects_potato_row() -> None:
    inherited = suggestion_for_text("814\u65e5", suggestion_version="V22_15_1")
    potato = suggestion_for_text(
        "Hoan thanh205\u5343\u5361/2",
        suggestion_version="V22_15_1",
    )

    assert inherited["source_text_corrected"] == "6\u670814\u65e5"
    assert potato["source_text_corrected"] == (
        "\u571f\u8c46 205\u5343\u5361/253.00\u514b"
    )
    assert potato["vi_text_suggested"] == (
        "Khoai t\u00e2y 205 kcal/253.00 g"
    )


def test_v22_16_corrects_scale_fragments_and_numeric_decimal() -> None:
    scale = suggestion_for_text(
        "\u4e00\u5728\u79e4\u4e0a", suggestion_version="V22_16_1"
    )
    grams = suggestion_for_text(
        "\u670800\u514b", suggestion_version="V22_16_1"
    )
    scale_fragment = suggestion_for_text(
        "\u79d1\u4e0a", suggestion_version="V22_16_1"
    )

    assert scale["source_text_corrected"] == "\u5728\u79e4\u4e0a"
    assert scale["vi_text_suggested"] == "Tr\u00ean c\u00e2n"
    assert scale_fragment["source_text_corrected"] == "\u5728\u79e4\u4e0a"
    assert grams["source_text_corrected"] == "170.00\u514b"
    assert grams["vi_text_suggested"] == "170.00 g"


def test_v22_16_corrects_mixed_food_rows_from_contact_sheet() -> None:
    tofu = suggestion_for_text(
        "Noidung toitilen\u5e72\u5361/06", suggestion_version="V22_16_1"
    )
    egg = suggestion_for_text(
        "\u5b9a\u4e49Suatan120\u5e72F/B6.00\u514b",
        suggestion_version="V22_16_1",
    )

    assert tofu["source_text_corrected"] == (
        "\u8c46\u8150 89\u5343\u5361/106.00\u514b"
    )
    assert tofu["vi_text_suggested"] == (
        "\u0110\u1eadu ph\u1ee5 89 kcal/106.00 g"
    )
    assert egg["source_text_corrected"] == (
        "\u9e21\u86cb 120\u5343\u5361/86.00\u514b"
    )
    assert egg["vi_text_suggested"] == "Tr\u1ee9ng 120 kcal/86.00 g"


def test_v22_16_reclassifies_real_label_and_decimal_cluster() -> None:
    edible = reclassification_for_cluster(
        "outres_c2e4234020f2", suggestion_version="V22_16_1"
    )
    grams = reclassification_for_cluster(
        "outres_9d9bd55044fa", suggestion_version="V22_16_1"
    )

    assert edible == ("\u53ef\u98df\u90e8", "Ph\u1ea7n \u0103n \u0111\u01b0\u1ee3c")
    assert grams == ("170.00\u514b", "170.00 g")


def test_v22_17_corrects_egg_ocr_variant() -> None:
    egg = suggestion_for_text(
        "\u5b9a\u4e49Suatan120\u5e72=/8.00\u514b",
        suggestion_version="V22_17_1",
    )

    assert egg["source_text_corrected"] == (
        "\u9e21\u86cb 120\u5343\u5361/86.00\u514b"
    )
    assert egg["vi_text_suggested"] == "Tr\u1ee9ng 120 kcal/86.00 g"


def test_v22_17_reclassifies_chickpea_source_label() -> None:
    result = reclassification_for_cluster(
        "outres_a634a0ee5fc3", suggestion_version="V22_17_1"
    )

    assert result == ("\u9e70\u5634\u8c46(\u5e72)", "\u0110\u1eadu g\u00e0 (kh\u00f4)")


def test_v22_42_reuses_approved_chicken_leg_metric_after_boundary_failure() -> None:
    result = reclassification_for_cluster(
        "outres_f28122ca48a6",
        suggestion_version="V22_42_2",
    )

    assert result == (
        "\u9e21\u817f 343\u5343\u5361/235.00\u514b",
        "\u0110\u00f9i g\u00e0 343 kcal/235.00 g",
    )


def test_v22_43_reuses_approved_chicken_breast_row_from_mixed_output_ocr() -> None:
    result = reclassification_for_cluster(
        "outres_6b265e1c7185",
        suggestion_version="V22_43_1",
    )

    assert result == (
        "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b",
        "\u1ee8c g\u00e0 208 kcal/176.00 g",
    )


def test_v22_44_reclassifies_mixed_oil_and_chicken_rows_from_evidence() -> None:
    oil = reclassification_for_cluster(
        "outres_ea75ce572045",
        suggestion_version="V22_44_1",
    )
    chicken = reclassification_for_cluster(
        "outres_50a7f3e47acd",
        suggestion_version="V22_44_1",
    )
    rejected_zero_gram = reclassification_for_cluster(
        "outres_7d6c805d76d6",
        suggestion_version="V22_44_1",
    )

    assert oil == (
        "\u82b1\u751f\u6cb9 45\u5343\u5361/5.00\u6beb\u5347",
        "D\u1ea7u \u0111\u1eadu ph\u1ed9ng 45 kcal/5.00 ml",
    )
    assert chicken == rejected_zero_gram == (
        "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b",
        "\u1ee8c g\u00e0 208 kcal/176.00 g",
    )


def test_v22_45_reclassifies_mixed_upload_and_mantou_row() -> None:
    result = reclassification_for_cluster(
        "outres_22b8fd370a00",
        suggestion_version="V22_45_1",
    )

    assert result == (
        "\u9992\u5934 192\u5343\u5361/86.00\u514b",
        "B\u00e1nh m\u00e0n th\u1ea7u 192 kcal/86.00 g",
    )


def test_v22_46_reclassifies_truncated_potato_metric() -> None:
    result = reclassification_for_cluster(
        "outres_eb01b86940a4",
        suggestion_version="V22_46_1",
    )

    assert result == (
        "\u571f\u8c46 205\u5343\u5361/253.00\u514b",
        "Khoai t\u00e2y 205 kcal/253.00 g",
    )


def test_v22_18_corrects_exact_scale_and_mixed_shrimp_row() -> None:
    scale = suggestion_for_text(
        "\u5728\u79e4\u4e0a", suggestion_version="V22_18_1"
    )
    shrimp = suggestion_for_text(
        "192 kcal/86.00g\u5e7200", suggestion_version="V22_18_1"
    )

    assert scale["vi_text_suggested"] == "Tr\u00ean c\u00e2n"
    assert shrimp["source_text_corrected"] == (
        "\u867e 99\u5343\u5361/106.00\u514b"
    )
    assert shrimp["vi_text_suggested"] == "T\u00f4m 99 kcal/106.00 g"


def test_v22_18_reclassifies_real_unit_oil_and_egg_labels() -> None:
    unit = reclassification_for_cluster(
        "outres_063238148f79", suggestion_version="V22_18_1"
    )
    oil = reclassification_for_cluster(
        "outres_eb6f3266292a", suggestion_version="V22_18_1"
    )
    egg = reclassification_for_cluster(
        "outres_651a45e6eba8", suggestion_version="V22_18_1"
    )

    assert unit == ("\u5343\u5361/\u5343\u7126", "kcal/kJ")
    assert oil == (
        "\u82b1\u751f\u6cb9 45\u5343\u5361/5.00\u6beb\u5347",
        "D\u1ea7u \u0111\u1eadu ph\u1ed9ng 45 kcal/5.00 ml",
    )
    assert egg == (
        "\u9e21\u86cb 120\u5343\u5361/86.00\u514b",
        "Tr\u1ee9ng 120 kcal/86.00 g",
    )


def test_v22_20_corrects_mixed_chicken_and_mantou_rows() -> None:
    chicken = suggestion_for_text(
        "Xac nhan them\u8111\u8089 n76.00x",
        suggestion_version="V22_20_1",
    )
    mantou = suggestion_for_text(
        "Cong thuRC\u5e72\u5361/860\u514b",
        suggestion_version="V22_20_1",
    )

    assert chicken["source_text_corrected"] == (
        "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b"
    )
    assert chicken["vi_text_suggested"] == (
        "\u1ee8c g\u00e0 208 kcal/176.00 g"
    )
    assert mantou["source_text_corrected"] == (
        "\u9992\u5934 192\u5343\u5361/86.00\u514b"
    )


def test_v22_20_reclassifies_real_fat_label_and_inherits_unit_label() -> None:
    fat = reclassification_for_cluster(
        "outres_a6f4cc53915a", suggestion_version="V22_20_1"
    )
    unit = reclassification_for_cluster(
        "outres_063238148f79", suggestion_version="V22_20_1"
    )

    assert fat == ("\u8102\u80aa\uff08\u514b\uff09", "Ch\u1ea5t b\u00e9o (g)")
    assert unit == ("\u5343\u5361/\u5343\u7126", "kcal/kJ")


def test_v22_21_corrects_protein_and_mixed_chicken_rows() -> None:
    protein = suggestion_for_text(
        "\u86cb\u767d\u4e48", suggestion_version="V22_21_1"
    )
    chicken = suggestion_for_text(
        "Tuy chinh\u9e21\u80f8\u8089E7e.0\u514b",
        suggestion_version="V22_21_1",
    )

    assert protein["source_text_corrected"] == (
        "\u86cb\u767d\u8d28\uff08\u514b\uff09"
    )
    assert protein["vi_text_suggested"] == "Ch\u1ea5t \u0111\u1ea1m (g)"
    assert chicken["source_text_corrected"] == (
        "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b"
    )


def test_v22_21_corrects_mixed_tofu_and_potato_rows() -> None:
    tofu = suggestion_for_text(
        "BatailenB\u5e74\u624be", suggestion_version="V22_21_1"
    )
    potato = suggestion_for_text(
        "Hoanthanh205\u5343\u536126", suggestion_version="V22_21_1"
    )

    assert tofu["source_text_corrected"] == (
        "\u8c46\u8150 89\u5343\u5361/106.00\u514b"
    )
    assert tofu["vi_text_suggested"] == (
        "\u0110\u1eadu ph\u1ee5 89 kcal/106.00 g"
    )
    assert potato["source_text_corrected"] == (
        "\u571f\u8c46 205\u5343\u5361/253.00\u514b"
    )


def test_v22_22_corrects_weight_value_and_boohee_brand() -> None:
    weight = suggestion_for_text(
        "\u8f6f\u91cd\u4fe1", suggestion_version="V22_22_1"
    )
    brand = suggestion_for_text(
        "\u901a\u8377\u5065\u5e8f", suggestion_version="V22_22_1"
    )

    assert weight["source_text_corrected"] == "\u79f0\u91cd\u503c"
    assert weight["vi_text_suggested"] == "Gi\u00e1 tr\u1ecb c\u00e2n"
    assert brand["source_text_corrected"] == "\u8584\u8377\u5065\u5eb7"
    assert brand["vi_text_suggested"] == "Boohee Health"


def test_v22_22_reclassifies_edible_and_fat_fragments() -> None:
    edible = reclassification_for_cluster(
        "outres_4302d8ed38fd", suggestion_version="V22_22_1"
    )
    fat = reclassification_for_cluster(
        "outres_3116ec6c0e7d", suggestion_version="V22_22_1"
    )

    assert edible == ("\u53ef\u98df\u90e8", "Ph\u1ea7n \u0103n \u0111\u01b0\u1ee3c")
    assert fat == ("\u8102\u80aa\uff08\u514b\uff09", "Ch\u1ea5t b\u00e9o (g)")


def test_v22_23_corrects_measuring_weight_and_scale_labels() -> None:
    measuring = suggestion_for_text(
        "\u6d4b\u91cf\u4e2d", suggestion_version="V22_23_1"
    )
    weight = suggestion_for_text(
        "\u4f60\u91cd\u503c10", suggestion_version="V22_23_1"
    )
    scale = suggestion_for_text(
        "\u5728\u79e4", suggestion_version="V22_23_1"
    )

    assert measuring["vi_text_suggested"] == "\u0110ang \u0111o"
    assert weight["source_text_corrected"] == "\u79f0\u91cd\u503c101"
    assert weight["vi_text_suggested"] == "Gi\u00e1 tr\u1ecb c\u00e2n: 101"
    assert scale["source_text_corrected"] == "\u5728\u79e4\u4e0a"


def test_v22_23_reclassifies_meal_time_and_fully_edible_labels() -> None:
    meal_time = reclassification_for_cluster(
        "outres_8c4f4c7126cd", suggestion_version="V22_23_1"
    )
    edible = reclassification_for_cluster(
        "outres_a603ae9c7ca2", suggestion_version="V22_23_1"
    )

    assert meal_time == ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n")
    assert edible == ("\u5168\u90e8\u53ef\u98df", "\u0102n \u0111\u01b0\u1ee3c to\u00e0n b\u1ed9")


def test_v22_24_reclassifies_mixed_meal_time_and_weight_residuals() -> None:
    meal_time = reclassification_for_cluster(
        "outres_e3c30c811a45", suggestion_version="V22_24_1"
    )
    weight = reclassification_for_cluster(
        "outres_5d22f4ca5ef3", suggestion_version="V22_24_1"
    )

    assert meal_time == ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n")
    assert weight == (
        "\u79f0\u91cd\u503c101",
        "Gi\u00e1 tr\u1ecb c\u00e2n: 101",
    )


def test_v22_24_inherits_v22_23_text_corrections() -> None:
    result = suggestion_for_text(
        "\u6d4b\u91cf\u4e2d", suggestion_version="V22_24_1"
    )

    assert result["source_text_corrected"] == "\u6d4b\u91cf\u4e2d"
    assert result["vi_text_suggested"] == "\u0110ang \u0111o"


def test_v22_25_reclassifies_mixed_tofu_residual_from_contact_sheet() -> None:
    result = reclassification_for_cluster(
        "outres_9e802017e3f2", suggestion_version="V22_25_1"
    )

    assert result == (
        "\u8c46\u8150 89\u5343\u5361/106.00\u514b",
        "\u0110\u1eadu ph\u1ee5 89 kcal/106.00 g",
    )


def test_v22_25_inherits_v22_24_cluster_corrections() -> None:
    result = reclassification_for_cluster(
        "outres_e3c30c811a45", suggestion_version="V22_25_1"
    )

    assert result == ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n")


def test_v22_26_reclassifies_fat_label_fragment() -> None:
    result = reclassification_for_cluster(
        "outres_976a35112da5", suggestion_version="V22_26_1"
    )

    assert result == ("\u8102\u80aa\uff08\u514b\uff09", "Ch\u1ea5t b\u00e9o (g)")


def test_v22_26_reclassifies_mixed_potato_row_from_phase2_authority() -> None:
    result = reclassification_for_cluster(
        "outres_268050156929", suggestion_version="V22_26_1"
    )

    assert result == (
        "\u571f\u8c46 205\u5343\u5361/253.00\u514b",
        "Khoai t\u00e2y 205 kcal/253.00 g",
    )


def test_v22_27_inherits_v22_26_fat_label_authority() -> None:
    result = reclassification_for_cluster(
        "outres_976a35112da5", suggestion_version="V22_27_1"
    )

    assert result == ("\u8102\u80aa\uff08\u514b\uff09", "Ch\u1ea5t b\u00e9o (g)")


def test_v22_28_reclassifies_scale_and_edible_fragments() -> None:
    scale = reclassification_for_cluster(
        "outres_7e8c4bddf4aa", suggestion_version="V22_28_1"
    )
    edible = reclassification_for_cluster(
        "outres_d90de50a2ba3", suggestion_version="V22_28_1"
    )

    assert scale == ("\u79f0\u91cd\u503c", "Gi\u00e1 tr\u1ecb c\u00e2n")
    assert edible == ("\u53ef\u98df\u90e8", "Ph\u1ea7n \u0103n \u0111\u01b0\u1ee3c")


def test_v22_29_reclassifies_both_meal_time_mixed_ocr_frames() -> None:
    first = reclassification_for_cluster(
        "outres_8f8d67f265f8", suggestion_version="V22_29_1"
    )
    second = reclassification_for_cluster(
        "outres_977da0505e39", suggestion_version="V22_29_1"
    )

    assert first == ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n")
    assert second == first


def test_v22_31_reclassifies_weight_and_meal_time_mixed_ocr() -> None:
    weight = reclassification_for_cluster(
        "outres_3d16c1a5a9a7", suggestion_version="V22_31_1"
    )
    meal = reclassification_for_cluster(
        "outres_60e4bf7e72fc", suggestion_version="V22_31_1"
    )

    assert weight == ("\u79f0\u91cd\u503c", "Tr\u1ecdng l\u01b0\u1ee3ng")
    assert meal == ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n")


def test_v22_37_reclassifies_edible_label_variants_from_contact_sheets() -> None:
    misread = reclassification_for_cluster(
        "outres_c93580143e22", suggestion_version="V22_37_2"
    )
    fragment = reclassification_for_cluster(
        "outres_2617b1c82d4a", suggestion_version="V22_37_2"
    )

    assert misread == ("\u53ef\u98df\u90e8", "Ph\u1ea7n \u0103n \u0111\u01b0\u1ee3c")
    assert fragment == misread


def test_v22_37_inherits_prior_cluster_corrections() -> None:
    inherited = reclassification_for_cluster(
        "outres_60e4bf7e72fc", suggestion_version="V22_37_2"
    )

    assert inherited == ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n")


def test_v22_39_reclassifies_mixed_ui_rows_from_phase2_and_contact_sheets() -> None:
    expected = {
        "outres_0903eb59a58d": ("\u7528\u9910\u65f6\u95f4", "Gi\u1edd \u0103n"),
        "outres_602a906b47d8": (
            "\u8102\u80aa\uff08\u514b\uff09",
            "Ch\u1ea5t b\u00e9o (g)",
        ),
        "outres_ce3b6e35bba3": (
            "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b",
            "\u1ee8c g\u00e0 208 kcal/176.00 g",
        ),
        "outres_16113eb3cab5": (
            "\u9e21\u817f 343\u5343\u5361/235.00\u514b",
            "\u0110\u00f9i g\u00e0 343 kcal/235.00 g",
        ),
        "outres_51cd2d0a203c": (
            "\u8d1d\u8d1d\u5357\u74dc 197\u5343\u5361/263.00\u514b",
            "B\u00ed \u0111\u1ecf Beibei 197 kcal/263.00 g",
        ),
    }

    for cluster_id, value in expected.items():
        assert reclassification_for_cluster(
            cluster_id, suggestion_version="V22_39_2"
        ) == value


def test_v22_40_reclassifies_both_pumpkin_ocr_variants() -> None:
    expected = (
        "\u8d1d\u8d1d\u5357\u74dc 197\u5343\u5361/263.00\u514b",
        "B\u00ed \u0111\u1ecf Beibei 197 kcal/263.00 g",
    )

    assert reclassification_for_cluster(
        "outres_feefb20b4e8b", suggestion_version="V22_40_1"
    ) == expected
    assert reclassification_for_cluster(
        "outres_51cd2d0a203c", suggestion_version="V22_40_1"
    ) == expected


def test_v22_48_normalizes_zero_gram_edge_fragment() -> None:
    assert reclassification_for_cluster(
        "outres_d3ec1617c72f", suggestion_version="V22_48_1"
    ) == ("0克", "0 g")


def test_v22_49_rebinds_panel_edge_suffix_to_potato_row() -> None:
    assert reclassification_for_cluster(
        "outres_d3ec1617c72f", suggestion_version="V22_49_1"
    ) == ("土豆 205千卡/253.00克", "Khoai tây 205 kcal/253.00 g")


def test_v22_50_restores_bottom_edge_breakfast_label() -> None:
    assert reclassification_for_cluster(
        "outres_d44d72c08aea", suggestion_version="V22_50_1"
    ) == ("早餐", "Bữa sáng")
