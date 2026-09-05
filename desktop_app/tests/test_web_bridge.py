import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from desktop_app.backend.domain.models import DocumentType, PersonData
from desktop_app.frontend.web_bridge import WebBridge
from desktop_app.frontend.web_bridge.schema import (
    resolve_company_profile_layout,
    resolve_document_tab_layout,
    resolve_representative_profile_layout,
)
from desktop_app.backend.validation import FieldError


class _FakeWindow:
    pass


class WebBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.bridge = WebBridge(_FakeWindow())
        # Bypass QSettings entirely so this test never touches the real
        # user's saved company/representative profile on disk.
        self.bridge.settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "CCCDReportTest", "unused")
        self.bridge.company_profile = PersonData()
        self.bridge.representative_profile = PersonData()

    def _run_generation(self, template: str, state: dict, folder: str) -> dict:
        """generate_service_template_documents now only dispatches a
        background DocumentGenerationWorker and returns {"ok": True,
        "job_id": ...} immediately -- the real result (paths/errors)
        arrives later via the generationFinished signal. Dispatch itself
        can also fail synchronously (overloaded / missing source images),
        in which case there's no job_id and nothing to wait for."""
        from PyQt5.QtCore import QEventLoop, QTimer

        dispatch = json.loads(self.bridge.generate_service_template_documents(
            template, json.dumps(state), folder,
        ))
        if not dispatch.get("job_id"):
            return dispatch

        captured = {}

        def on_finished(job_id, result_json):
            if job_id == dispatch["job_id"]:
                captured["result"] = json.loads(result_json)
                loop.quit()

        self.bridge.generationFinished.connect(on_finished)
        loop = QEventLoop()
        QTimer.singleShot(30000, loop.quit)
        loop.exec_()
        self.bridge.generationFinished.disconnect(on_finished)
        self.assertIn("result", captured, "generationFinished never fired within 30s")
        return captured["result"]

    def test_representative_profile_round_trips_and_validates(self):
        incomplete = json.loads(self.bridge.save_representative_profile(json.dumps({"full_name": "LE THI DAI DIEN"})))
        self.assertFalse(incomplete["ok"])
        self.assertTrue(all(e["path"].startswith("representative.") for e in incomplete["errors"]))

        complete = {
            "full_name": "LE THI DAI DIEN", "id_number": "001090001234", "date_of_birth": "01/01/1990",
            "issue_date": "01/01/2022", "issue_place": "Cục Cảnh sát QLHC về TTXH",
            "nationality": "Việt Nam", "address": "10 Xã Đàn, Hà Nội",
        }
        result = json.loads(self.bridge.save_representative_profile(json.dumps(complete)))
        self.assertTrue(result["ok"], result)
        self.assertEqual(json.loads(self.bridge.get_representative_profile())["full_name"], "LE THI DAI DIEN")

    def test_representative_2_profile_round_trips_independently_of_representative_1(self):
        incomplete = json.loads(self.bridge.save_representative_2_profile(json.dumps({"full_name": "LE VAN DAI DIEN 2"})))
        self.assertFalse(incomplete["ok"])
        self.assertTrue(all(e["path"].startswith("representative_2.") for e in incomplete["errors"]))

        complete = {
            "full_name": "LE VAN DAI DIEN 2", "id_number": "001090005678", "date_of_birth": "02/02/1985",
            "issue_date": "02/02/2022", "issue_place": "Cục Cảnh sát QLHC về TTXH",
            "nationality": "Việt Nam", "address": "20 Xã Đàn, Hà Nội",
        }
        result = json.loads(self.bridge.save_representative_2_profile(json.dumps(complete)))
        self.assertTrue(result["ok"], result)
        self.assertEqual(json.loads(self.bridge.get_representative_2_profile())["full_name"], "LE VAN DAI DIEN 2")
        # A completely separate profile from "Người đại diện" 1 -- saving
        # this one must never touch representative_profile's own record.
        self.assertNotEqual(
            json.loads(self.bridge.get_representative_profile())["full_name"], "LE VAN DAI DIEN 2",
        )

    def test_clear_signature_slots_revert_to_plain_cursive_text(self):
        # Doesn't go through save_cropped_signature (writes to the real,
        # non-test-isolated AppData signatures dir -- see _signatures_dir)
        # -- sets a fake path directly, same effective state.
        self.bridge.representative_profile.signature_path = "/tmp/fake_representative.png"
        result = json.loads(self.bridge.clear_representative_signature())
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.bridge.representative_profile.signature_path, "")
        self.assertEqual(json.loads(self.bridge.get_representative_profile())["signature_path"], "")

        self.bridge.representative_2_profile.signature_path = "/tmp/fake_representative_2.png"
        result = json.loads(self.bridge.clear_representative_2_signature())
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.bridge.representative_2_profile.signature_path, "")
        self.assertEqual(json.loads(self.bridge.get_representative_2_profile())["signature_path"], "")

        from desktop_app.frontend.web_bridge import PROVIDER_SIGNATURE_SETTINGS_KEY

        self.bridge.settings.setValue(PROVIDER_SIGNATURE_SETTINGS_KEY, "/tmp/fake_provider.png")
        result = json.loads(self.bridge.clear_provider_signature())
        self.assertTrue(result["ok"], result)
        self.assertEqual(json.loads(self.bridge.get_provider_signature())["signature_path"], "")

    def test_dynamic_clerks_cover_seven_services_without_overlap(self):
        profiles = [
            {
                "profile_id": "operator_1",
                "name": "NGUYỄN GIAO DỊCH",
                "service_templates": [
                    "prepaid_transfer_org", "prepaid_transfer_individual",
                    "commitment_transfer_individual", "commitment_transfer_org",
                    "quang_ha_stt",
                ],
            },
            {
                "profile_id": "operator_2",
                "name": "TRẦN THAY SIM",
                "service_templates": ["sim_replacement", "quang_ha_sim_ck"],
            },
        ]
        result = json.loads(self.bridge.save_operator_profiles(json.dumps(profiles)))
        self.assertTrue(result["ok"], result)
        payload = json.loads(self.bridge.get_operator_profiles())
        self.assertEqual(len(payload["profiles"]), 2)
        self.assertEqual(len(payload["services"]), 7)

        duplicate = [dict(item) for item in profiles]
        duplicate[1] = {
            **duplicate[1],
            "service_templates": ["sim_replacement", "prepaid_transfer_org"],
        }
        rejected = json.loads(self.bridge.save_operator_profiles(json.dumps(duplicate)))
        self.assertFalse(rejected["ok"])
        self.assertIn("chỉ được giao cho một người", rejected["message"])

    def test_document_set_settings_default_to_all_documents_and_can_be_overridden(self):
        from desktop_app.backend.domain.models import ServiceTemplate

        default = json.loads(self.bridge.get_document_set_settings())
        self.assertEqual(len(default["services"]), 7)
        self.assertEqual(len(default["documents"]), 7)
        self.assertEqual(
            set(default["selected"][ServiceTemplate.SIM_REPLACEMENT.value]),
            {"aftersale", "sim_change_form"},
        )

        selected = default["selected"]
        selected[ServiceTemplate.PREPAID_TRANSFER_ORG.value] = ["transfer", "aftersale"]
        saved = json.loads(self.bridge.save_document_set_settings(json.dumps(selected)))
        self.assertTrue(saved["ok"], saved)

        reloaded = json.loads(self.bridge.get_document_set_settings())
        self.assertEqual(
            reloaded["selected"][ServiceTemplate.PREPAID_TRANSFER_ORG.value],
            ["transfer", "aftersale"],
        )
        # on_service_template_changed must reflect the override immediately.
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": ServiceTemplate.PREPAID_TRANSFER_ORG.value,
            "state": json.loads(self.bridge.get_initial_state())["state"],
        })))
        self.assertEqual(response["ui"]["documentCount"], 2)

    def test_document_set_settings_reject_a_service_with_zero_documents(self):
        from desktop_app.backend.domain.models import ServiceTemplate

        selected = json.loads(self.bridge.get_document_set_settings())["selected"]
        selected[ServiceTemplate.SIM_REPLACEMENT.value] = []
        rejected = json.loads(self.bridge.save_document_set_settings(json.dumps(selected)))
        self.assertFalse(rejected["ok"])
        self.assertIn("cần chọn ít nhất một tài liệu", rejected["message"])

    def test_company_and_shop_identity_fields_auto_fill_from_profiles(self):
        self.bridge.company_profile = PersonData(
            entity_type="Tổ chức", organization_name="CÔNG TY ABC",
            business_registration_number="0101234567", business_registration_issue_date="01/01/2020",
            business_registration_issue_place="Sở KHĐT Hà Nội", headquarters_address="1 Xã Đàn",
            phone="02412345678", phone_2="0987000111",
        )
        self.bridge.representative_profile = PersonData(full_name="LÊ THỊ ĐẠI DIỆN")

        defaults = self.bridge._default_report_dict()
        self.assertEqual(defaults["shop_id_number"], "0101234567")
        self.assertEqual(defaults["shop_issue_date"], "01/01/2020")
        self.assertEqual(defaults["shop_issue_place"], "Sở KHĐT Hà Nội")
        self.assertEqual(defaults["shop_phone"], "02412345678")
        self.assertEqual(defaults["shop_phone_2"], "0987000111")

        request = {
            "previous_document_type": "", "new_document_type": "aftersale",
            "state": {**defaults, "document_type": "aftersale"},
        }
        response = json.loads(self.bridge.on_document_type_changed(json.dumps(request)))
        # provider_representative (Bên B / "Đại diện bên cung cấp dịch vụ")
        # is Vietnamobile's own fixed signing identity -- always Võ Duy
        # Nhật, regardless of whatever is filled into "Người đại diện"
        # (representative_profile feeds a DIFFERENT role: the org-party
        # representative for TRANSFER's old owner, etc.). A real user report
        # ("tôi đã bảo provider_representative là Võ Duy Nhật rồi mà") caught
        # this defaulting to the representative profile's own name instead.
        self.assertEqual(response["state_patch"]["provider_representative"], "VÕ DUY NHẬT")

        reset = json.loads(self.bridge.apply_profile_defaults("transfer"))
        self.assertEqual(reset["customer"]["organization_name"], "CÔNG TY ABC")
        self.assertEqual(reset["customer"]["full_name"], "LÊ THỊ ĐẠI DIỆN")

    def test_prepaid_contract_pulls_representative_phone_and_email(self):
        self.bridge.representative_profile = PersonData(
            full_name="LÊ THỊ ĐẠI DIỆN", phone="0909888777", email="daidien@example.com",
        )
        defaults = self.bridge._default_report_dict()
        request = {
            "previous_document_type": "", "new_document_type": "prepaid_contract",
            "state": {**defaults, "document_type": "prepaid_contract"},
        }
        response = json.loads(self.bridge.on_document_type_changed(json.dumps(request)))
        patch = response["state_patch"]
        self.assertEqual(patch["provider_phone"], "0909888777")
        self.assertEqual(patch["provider_email"], "daidien@example.com")

    def test_prepaid_contract_has_five_semantic_tabs_and_shared_person_forms(self):
        self.bridge.company_profile = PersonData(
            entity_type="Tổ chức", organization_name="CÔNG TY ABC",
            business_registration_number="0101234567",
            business_registration_issue_date="01/01/2020",
            business_registration_issue_place="Sở KHĐT Hà Nội",
            headquarters_address="1 Xã Đàn", representative_name="ĐẠI DIỆN BÊN B",
        )
        self.bridge.representative_profile = PersonData(
            full_name="LÊ THỊ ĐẠI DIỆN", id_number="001090001234",
            date_of_birth="01/01/1990", issue_date="01/01/2022",
            issue_place="Cục Cảnh sát QLHC về TTXH", nationality="Việt Nam",
            address="10 Xã Đàn", phone="0909888777", email="rep@example.com",
        )
        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_document_type_changed(json.dumps({
            "previous_document_type": "", "new_document_type": "prepaid_contract",
            "state": {**defaults, "document_type": "prepaid_contract"},
        })))

        tabs = response["ui"]["tabs"]
        self.assertEqual(
            [tabs["customerLabel"], tabs["representativeLabel"], tabs["newOwnerLabel"],
             tabs["documentLabel"], tabs["simsLabel"]],
            ["Công ty", "Người đại diện", "Khách hàng",
             "Bên cung cấp dịch vụ viễn thông", "Danh sách số SIM và ngày hòa mạng"],
        )
        self.assertTrue(tabs["representativeTabVisible"])
        self.assertTrue(tabs["newOwnerTabVisible"])
        self.assertTrue(tabs["simsTabVisible"])
        self.assertEqual(response["state_patch"]["representative"]["full_name"], "LÊ THỊ ĐẠI DIỆN")
        self.assertEqual(response["state_patch"]["representative"]["representative_position"], "Giám đốc")

        representative_fields = [
            cell["field"] for row in response["layouts"]["representative"]["primary_rows"] for cell in row
        ]
        position = next(field for field in representative_fields if field["name"] == "representative_position")
        self.assertEqual(position["options"], ["Giám đốc", "Nhân viên"])
        representative_phone = next(field for field in representative_fields if field["name"] == "phone")
        self.assertFalse(representative_phone["required"])
        self.assertTrue({"phone", "email", "other_contact"}.issubset(
            {field["name"] for field in representative_fields}
        ))
        customer_names = {
            cell["field"]["name"]
            for row in response["layouts"]["new_owner"]["primary_rows"] for cell in row
        }
        self.assertTrue({"phone", "email", "other_contact"}.issubset(customer_names))
        customer_fields = [
            cell["field"]
            for row in response["layouts"]["new_owner"]["primary_rows"]
            for cell in row
        ]
        customer_phone = next(field for field in customer_fields if field["name"] == "phone")
        self.assertFalse(customer_phone["required"])
        self.assertEqual(len(response["layouts"]["document"]["sections"]), 2)
        provider_fields = [
            cell["field"]
            for section in response["layouts"]["document"]["sections"]
            for row in section["rows"]
            for cell in row
        ]
        service_point = next(field for field in provider_fields if field["name"] == "service_point_name")
        registration_time = next(field for field in provider_fields if field["name"] == "registration_time")
        self.assertFalse(service_point["required"])
        self.assertFalse(registration_time["required"])
        self.assertEqual(response["layouts"]["sims"]["max_rows"], 5)

    def test_company_profile_layout_keeps_only_company_information(self):
        company_rows = resolve_company_profile_layout()["primary_rows"]
        self.assertEqual(len(company_rows), 4)
        self.assertEqual(
            [[cell["field"]["name"] for cell in row] for row in company_rows],
            [
                ["organization_name", "business_registration_number"],
                ["business_registration_issue_date", "business_registration_issue_place"],
                ["phone", "phone_2"],
                ["headquarters_address"],
            ],
        )
        self.assertEqual(len(resolve_representative_profile_layout()["primary_rows"]), 3)

    def test_document_copy_is_not_overwritten_until_defaults_are_explicitly_applied(self):
        self.bridge.company_profile = PersonData(
            entity_type="Tổ chức",
            organization_name="CÔNG TY MẶC ĐỊNH",
            business_registration_number="0101234567",
            business_registration_issue_date="01/01/2020",
            business_registration_issue_place="Sở KHĐT Hà Nội",
            headquarters_address="1 Xã Đàn",
        )
        self.bridge.representative_profile = PersonData(
            full_name="ĐẠI DIỆN MẶC ĐỊNH",
            id_number="001090001234",
            issue_date="01/01/2022",
            issue_place="Cục Cảnh sát QLHC về TTXH",
            date_of_birth="01/01/1990",
            nationality="Việt Nam",
            address="Địa chỉ người đại diện",
        )
        customized = PersonData(
            entity_type="Tổ chức",
            organization_name="CÔNG TY SỬA RIÊNG",
            business_registration_number="9999999999",
            business_registration_issue_date="02/02/2022",
            business_registration_issue_place="Nơi sửa riêng",
            headquarters_address="Địa chỉ sửa riêng",
            full_name="ĐẠI DIỆN SỬA RIÊNG",
        )
        state = self.bridge._default_report_dict()
        state.update({"document_type": "transfer", "customer": customized.__dict__})
        response = json.loads(self.bridge.on_document_type_changed(json.dumps({
            "previous_document_type": "aftersale",
            "new_document_type": "transfer",
            "state": state,
            "apply_profile_defaults": False,
            "preserve_subject": False,
        })))
        self.assertEqual(
            response["state_patch"]["customer"]["organization_name"],
            "CÔNG TY SỬA RIÊNG",
        )

        reset = json.loads(self.bridge.apply_profile_defaults("transfer"))
        self.assertEqual(reset["customer"]["organization_name"], "CÔNG TY MẶC ĐỊNH")
        self.assertEqual(reset["customer"]["full_name"], "ĐẠI DIỆN MẶC ĐỊNH")

    def test_transfer_uses_switchable_party_forms_and_contract_layout(self):
        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_document_type_changed(json.dumps({
            "previous_document_type": "",
            "new_document_type": "transfer",
            "state": {**defaults, "document_type": "transfer", "transfer_time": "03:45"},
        })))

        self.assertEqual(response["state_patch"]["customer"]["entity_type"], "Tổ chức")
        self.assertEqual(response["state_patch"]["new_owner"]["entity_type"], "Cá nhân")
        self.assertEqual(response["state_patch"]["transfer_time"], "03")
        self.assertFalse(response["ui"]["tabs"]["representativeTabVisible"])
        self.assertFalse(response["ui"]["tabs"]["simsTabVisible"])
        self.assertTrue(response["layouts"]["customer"]["allow_entity"])
        self.assertEqual(
            [[cell["field"]["name"] for cell in row] for row in response["layouts"]["customer"]["primary_rows"]],
            [
                ["entity_type", "organization_name"],
                ["headquarters_address", "business_registration_number"],
                ["full_name", "id_number", "issue_date"],
                ["issue_place", "date_of_birth", "nationality"],
                ["address"],
            ],
        )
        self.assertEqual(
            [[cell["field"]["name"] for cell in row] for row in response["layouts"]["new_owner"]["primary_rows"]],
            [
                ["entity_type"],
                ["full_name", "id_number", "issue_date"],
                ["issue_place", "date_of_birth", "nationality"],
                ["address"],
            ],
        )
        self.assertEqual(
            [[cell["field"]["name"] for cell in row] for row in response["layouts"]["document"]["primary_rows"]],
            [
                ["document_date", "payment_method"],
                ["source_contract_number", "source_contract_date", "registration_form_date"],
                ["transfer_time", "transfer_effective_date"],
            ],
        )

        individual = PersonData(entity_type="Cá nhân", full_name="BÊN A CÁ NHÂN")
        individual_response = json.loads(self.bridge.on_document_type_changed(json.dumps({
            "previous_document_type": "transfer",
            "new_document_type": "transfer",
            "state": {**defaults, "document_type": "transfer", "customer": individual.__dict__},
            "apply_profile_defaults": False,
            "preserve_subject": False,
        })))
        self.assertEqual(
            individual_response["state_patch"]["customer"]["entity_type"], "Cá nhân"
        )

        organization_layout = json.loads(
            self.bridge.on_entity_type_changed("new_owner", "Tổ chức")
        )
        self.assertEqual(
            [[cell["field"]["name"] for cell in row] for row in organization_layout["primary_rows"]],
            [
                ["entity_type", "organization_name"],
                ["headquarters_address", "business_registration_number"],
                ["full_name", "id_number", "issue_date"],
                ["issue_place", "date_of_birth", "nationality"],
                ["address"],
            ],
        )

    def test_company_profile_saves_only_the_fields_shown_by_company_form(self):
        company = {
            "organization_name": "CÔNG TY ABC",
            "business_registration_number": "0101234567",
            "business_registration_issue_date": "01/01/2020",
            "business_registration_issue_place": "Sở KHĐT Hà Nội",
            "phone": "0241234567",
            "phone_2": "0987654321",
            "headquarters_address": "1 Xã Đàn, Hà Nội",
        }
        result = json.loads(self.bridge.save_company_profile(json.dumps(company)))
        self.assertTrue(result["ok"], result)

    def test_aftersale_uses_organization_customer_and_minimal_document_tabs(self):
        layout = resolve_document_tab_layout(DocumentType.AFTERSALE)
        common_names = {cell["field"]["name"] for row in layout["common_rows"] for cell in row}
        self.assertEqual(common_names, set())
        primary_names = {cell["field"]["name"] for row in layout["primary_rows"] for cell in row}
        self.assertEqual(primary_names, {"service_action", "attachments", "other_attachment"})
        self.assertIsNone(layout["notes_field"])

        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_document_type_changed(json.dumps({
            "previous_document_type": "",
            "new_document_type": "aftersale",
            "state": {**defaults, "document_type": "aftersale"},
        })))
        self.assertEqual(response["ui"]["tabs"]["customerLabel"], "Tổ chức")
        self.assertEqual(response["ui"]["tabs"]["newOwnerLabel"], "Khách hàng")
        self.assertTrue(response["ui"]["tabs"]["newOwnerTabVisible"])
        self.assertFalse(response["ui"]["tabs"]["newOwnerUploadVisible"])
        self.assertFalse(response["ui"]["tabs"]["representativeTabVisible"])
        self.assertFalse(response["ui"]["tabs"]["simsTabVisible"])
        self.assertEqual(
            [[cell["field"]["name"] for cell in row] for row in response["layouts"]["new_owner"]["primary_rows"]],
            [["full_name", "id_number"], ["issue_date", "issue_place"]],
        )

    def test_beautiful_number_table_uses_numeric_months_and_has_no_bottom_notes(self):
        layout = resolve_document_tab_layout(DocumentType.BEAUTIFUL_NUMBER)
        self.assertIsNone(layout["notes_field"])
        table = layout["primary_rows"][0][0]["field"]
        self.assertEqual(table["kind"], "subscriber_table")
        self.assertEqual(table["list_path"], "beautiful_subscribers")
        month_column = next(column for column in table["columns"] if column["name"] == "commitment_months")
        self.assertEqual(month_column["kind"], "number")
        fee_column = next(column for column in table["columns"] if column["name"] == "monthly_fee")
        self.assertEqual(fee_column["kind"], "number")
        self.assertIn("nghìn đồng", fee_column["label"])

    def test_beautiful_number_initializes_an_unlimited_row_list(self):
        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_document_type_changed(json.dumps({
            "previous_document_type": "", "new_document_type": "beautiful_number",
            "state": {**defaults, "document_type": "beautiful_number", "subscriber_number": "0925123456"},
        })))
        rows = response["state_patch"]["beautiful_subscribers"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["subscriber_number"], "0925123456")

    def test_get_service_templates_lists_all_seven_mau(self):
        templates = json.loads(self.bridge.get_service_templates())
        self.assertEqual(len(templates), 7)
        self.assertEqual({t["value"] for t in templates}, {
            "prepaid_transfer_org", "prepaid_transfer_individual",
            "commitment_transfer_individual", "commitment_transfer_org", "sim_replacement",
            "quang_ha_stt", "quang_ha_sim_ck",
        })

    def test_on_service_template_changed_sets_entity_types_and_document_set(self):
        defaults = self.bridge._default_report_dict()
        cases = [
            ("prepaid_transfer_org", 4, "Tổ chức"),
            ("prepaid_transfer_individual", 4, "Cá nhân"),
            ("commitment_transfer_individual", 4, "Cá nhân"),
            ("commitment_transfer_org", 4, "Tổ chức"),
            ("sim_replacement", 2, "Cá nhân"),
        ]
        for value, expected_count, expected_entity in cases:
            with self.subTest(template=value):
                response = json.loads(self.bridge.on_service_template_changed(json.dumps({
                    "previous_service_template": "", "new_service_template": value,
                    "state": {**defaults, "document_type": ""},
                })))
                self.assertTrue(response["ui"]["ready"])
                self.assertEqual(response["ui"]["documentCount"], expected_count)
                self.assertEqual(response["state_patch"]["customer"]["entity_type"], expected_entity)
                self.assertEqual(response["state_patch"]["new_owner"]["entity_type"], "Cá nhân")
                self.assertNotIn("layouts", response)
                self.assertNotIn("advanced_layouts", response)
                self.assertNotIn("documentTypes", response["ui"])
                self.assertEqual(
                    [tab["id"] for tab in response["service_layout"]["tabs"]],
                    ["current_owner", "new_owner", "provider", "transaction"],
                )
        service_actions = {
            "prepaid_transfer_org": "Chuyển chủ quyền", "sim_replacement": "Thay SIM",
        }
        for value, action in service_actions.items():
            response = json.loads(self.bridge.on_service_template_changed(json.dumps({
                "previous_service_template": "", "new_service_template": value,
                "state": {**defaults, "document_type": ""},
            })))
            self.assertEqual(response["state_patch"]["service_action"], action)

    def test_sim_replacement_customer_tab_has_no_phone_email_gender_inputs(self):
        # sim_change_form's own template prints {{sim_customer_phone}}/
        # {{sim_customer_email}}/{{sim_customer_gender}} for this party, but
        # per direct instruction: phone is the SHOP's own number (auto-
        # defaulted from the company profile, not typed per case -- see
        # renderer.py's sim_customer_phone), and email/gender simply aren't
        # needed at all. None of the 3 get a manual UI input.
        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": "sim_replacement",
            "state": {**defaults, "document_type": ""},
        })))
        paths = {
            cell["field"]["path"]
            for section in response["service_layout"]["current_owner"]["sections"]
            for row in section["rows"]
            for cell in row
        }
        self.assertNotIn("customer.phone", paths)
        self.assertNotIn("customer.email", paths)
        self.assertNotIn("customer.gender", paths)

    def test_common_dossier_is_the_identity_source_across_service_switches(self):
        defaults = self.bridge._default_report_dict()
        common = {
            "revision": 7,
            "person123": {
                "entity_type": "Cá nhân", "full_name": "NGƯỜI TRONG ẢNH 1-3",
                "id_number": "001099999991", "nationality": "Việt Nam",
            },
            "person456": {
                "entity_type": "Cá nhân", "full_name": "NGƯỜI TRONG ẢNH 4-6",
                "id_number": "001099999992", "nationality": "Việt Nam",
            },
        }

        def switch(service: str, contaminated_state: dict | None = None):
            return json.loads(self.bridge.on_service_template_changed(json.dumps({
                "previous_service_template": "",
                "new_service_template": service,
                "state": contaminated_state or {**defaults, "document_type": ""},
                "common_dossier": common,
            })))["state_patch"]

        individual = switch("prepaid_transfer_individual")
        self.assertEqual(individual["customer"]["full_name"], "NGƯỜI TRONG ẢNH 1-3")
        self.assertEqual(individual["new_owner"]["full_name"], "NGƯỜI TRONG ẢNH 4-6")

        # In an organization service the exact same 1-3 slot changes role
        # to new owner; it must never be copied into the organization.
        organization = switch("prepaid_transfer_org", {
            **defaults,
            "document_type": "transfer",
            "customer": {"full_name": "DỮ LIỆU NGỮ NGHĨA CŨ BỊ NHIỄM"},
            "new_owner": {"full_name": "DỮ LIỆU NGỮ NGHĨA CŨ BỊ NHIỄM"},
        })
        self.assertEqual(organization["new_owner"]["full_name"], "NGƯỜI TRONG ẢNH 1-3")
        self.assertNotEqual(organization["customer"].get("full_name"), "NGƯỜI TRONG ẢNH 1-3")

        sim = switch("sim_replacement")
        self.assertEqual(sim["customer"]["full_name"], "NGƯỜI TRONG ẢNH 1-3")
        self.assertNotIn("full_name", sim["new_owner"])

    def test_quang_ha_stt_customer_comes_from_representative_2_not_ocr(self):
        # Bên A ("người thực hiện chuyển chủ quyền") is the fixed "Người
        # đại diện 2" profile for this service specifically -- unlike
        # every other template, person123 (the scanned photo) becomes the
        # NEW subscriber (new_owner), never the customer.
        complete = {
            "full_name": "PHAM DAI DIEN HAI", "id_number": "001090009999", "date_of_birth": "03/03/1980",
            "issue_date": "03/03/2022", "issue_place": "Cục Cảnh sát QLHC về TTXH",
            "nationality": "Việt Nam", "address": "30 Xã Đàn, Hà Nội",
        }
        saved = json.loads(self.bridge.save_representative_2_profile(json.dumps(complete)))
        self.assertTrue(saved["ok"], saved)

        defaults = self.bridge._default_report_dict()
        common = {
            "revision": 1,
            "person123": {
                "entity_type": "Cá nhân", "full_name": "THUE BAO MOI QUET QR",
                "id_number": "001099999993", "nationality": "Việt Nam",
            },
        }
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": "quang_ha_stt",
            "state": {**defaults, "document_type": ""},
            "common_dossier": common,
        })))
        state_patch = response["state_patch"]
        self.assertEqual(state_patch["customer"]["full_name"], "PHAM DAI DIEN HAI")
        self.assertEqual(state_patch["new_owner"]["full_name"], "THUE BAO MOI QUET QR")

    def test_common_ocr_batches_can_run_in_parallel_but_legacy_scan_still_reports_busy(self):
        with (
            patch.object(self.bridge, "_ocr_busy", return_value=True),
            patch.object(self.bridge, "_start_ocr", return_value=True) as start,
        ):
            common = json.loads(self.bridge.submit_folder_images(
                "common_456:9", json.dumps(["4.jpg", "5.jpg"]),
            ))
            legacy = json.loads(self.bridge.submit_folder_images(
                "customer", json.dumps(["1.jpg", "2.jpg"]),
            ))
        self.assertTrue(common["started"])
        start.assert_called_once()
        self.assertFalse(legacy["started"])
        self.assertIn("đang hoàn tất", legacy["message"])

    def test_service_form_controls_tabs_and_one_subscriber_table(self):
        defaults = self.bridge._default_report_dict()
        initial = json.loads(self.bridge.get_initial_state())
        subscriber_layout = initial["subscriber_layout"]
        self.assertEqual(
            [column["name"] for column in subscriber_layout["columns"]],
            [
                "subscriber_number", "commitment_months", "monthly_fee",
                "sim_serial", "activation_date",
            ],
        )
        self.assertEqual(subscriber_layout["max_rows"], 5)

        def layout_for(service):
            return json.loads(self.bridge.on_service_template_changed(json.dumps({
                "previous_service_template": "", "new_service_template": service,
                "state": {**defaults, "document_type": ""},
            })))["service_layout"]

        prepaid = layout_for("prepaid_transfer_org")
        self.assertNotIn("subscribers", prepaid)
        self.assertEqual(
            [tab["label"] for tab in prepaid["tabs"] if tab["visible"]],
            ["Tổ chức", "Chủ mới", "Đơn vị thực hiện"],
        )
        self.assertTrue(next(tab for tab in prepaid["tabs"] if tab["id"] == "provider")["visible"])

        commitment = layout_for("commitment_transfer_individual")
        self.assertEqual(
            [tab["label"] for tab in commitment["tabs"] if tab["visible"]],
            ["Chủ cũ", "Chủ mới", "Đơn vị thực hiện"],
        )

        sim = layout_for("sim_replacement")
        self.assertEqual(
            [tab["label"] for tab in sim["tabs"] if tab["visible"]],
            ["Người yêu cầu", "Giao dịch"],
        )
        self.assertFalse(next(tab for tab in sim["tabs"] if tab["id"] == "new_owner")["visible"])

    def test_service_source_roles_match_the_correct_numbered_images(self):
        templates = {item["value"]: item for item in json.loads(self.bridge.get_service_templates())}
        for service in ("prepaid_transfer_org", "commitment_transfer_org", "quang_ha_stt"):
            self.assertEqual(templates[service]["source_role"], "new_owner_123")
            self.assertEqual(templates[service]["required_images"], [1, 2, 3])
        for service in ("prepaid_transfer_individual", "commitment_transfer_individual"):
            self.assertEqual(templates[service]["source_role"], "old_123_new_456")
            self.assertEqual(templates[service]["required_images"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(templates["sim_replacement"]["source_role"], "requester_123")

    def test_service_generation_maps_internal_subscriber_errors_to_the_fixed_form(self):
        import tempfile

        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "",
            "new_service_template": "commitment_transfer_individual",
            "state": {**defaults, "document_type": ""},
        })))
        state = {**defaults, **response["state_patch"]}
        with tempfile.TemporaryDirectory() as folder, patch(
            "desktop_app.frontend.web_bridge.generate_service_template",
            return_value=([], [
                FieldError("beautiful_subscribers.0.monthly_fee", "Cước không hợp lệ"),
                FieldError("subscriber_number", "Thiếu số thuê bao"),
            ]),
        ):
            for number in range(1, 7):
                Path(folder, f"{number}.jpg").write_bytes(b"source")
            self.bridge._last_source_dir = folder
            result = self._run_generation("commitment_transfer_individual", state, folder)
        self.assertEqual(
            [error["path"] for error in result["errors"]],
            ["subscribers.0.monthly_fee", "subscribers.0.subscriber_number"],
        )

    def test_individual_service_preserves_scanned_old_owner_and_separates_provider_company(self):
        self.bridge.company_profile = PersonData(
            entity_type="Tổ chức", organization_name="CÔNG TY CUNG CẤP",
            business_registration_number="0101234567",
            business_registration_issue_date="01/01/2020",
            business_registration_issue_place="Sở Tài chính Hà Nội",
            headquarters_address="1 Xã Đàn",
        )
        defaults = self.bridge._default_report_dict()
        scanned = PersonData(
            full_name="CHỦ CŨ CÁ NHÂN", id_number="001099999999",
            issue_date="01/01/2021", issue_place="Cục Cảnh sát",
            date_of_birth="01/01/1990", nationality="Việt Nam", address="Hà Nội",
        )
        state = {**defaults, "document_type": "", "customer": scanned.__dict__}
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": "prepaid_transfer_individual",
            "state": state,
        })))
        self.assertEqual(response["state_patch"]["customer"]["full_name"], "CHỦ CŨ CÁ NHÂN")
        self.assertEqual(response["state_patch"]["customer"]["id_number"], "001099999999")
        self.assertEqual(
            response["state_patch"]["provider_company"]["organization_name"],
            "CÔNG TY CUNG CẤP",
        )

    def test_organization_service_never_treats_images_123_as_its_representative(self):
        self.bridge.company_profile = PersonData(
            entity_type="Tổ chức", organization_name="CÔNG TY CHỦ CŨ",
            business_registration_number="0101234567",
            business_registration_issue_date="01/01/2020",
            business_registration_issue_place="Sở Tài chính Hà Nội",
            headquarters_address="1 Xã Đàn",
        )
        self.bridge.representative_profile = PersonData(
            full_name="NGƯỜI ĐẠI DIỆN MẶC ĐỊNH", id_number="001090001234",
            issue_date="01/01/2022", issue_place="Cục Cảnh sát",
            date_of_birth="01/01/1990", nationality="Việt Nam", address="Hà Nội",
        )
        defaults = self.bridge._default_report_dict()
        image_123_person = PersonData(
            full_name="CHỦ MỚI TRONG ẢNH", id_number="001099999999",
            issue_date="01/01/2021", issue_place="Cục Cảnh sát",
            date_of_birth="01/01/1999", nationality="Việt Nam", address="Hà Nội",
        )
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "",
            "new_service_template": "prepaid_transfer_org",
            "state": {**defaults, "customer": image_123_person.__dict__},
        })))
        customer = response["state_patch"]["customer"]
        self.assertEqual(customer["organization_name"], "CÔNG TY CHỦ CŨ")
        self.assertEqual(customer["full_name"], "NGƯỜI ĐẠI DIỆN MẶC ĐỊNH")
        self.assertNotEqual(customer["id_number"], image_123_person.id_number)

    def test_default_output_dir_persists_and_falls_back(self):
        fallback = json.loads(self.bridge.get_default_output_dir())
        self.assertTrue(fallback)
        self.bridge.set_default_output_dir("/tmp/cccd_custom_output")
        self.assertEqual(json.loads(self.bridge.get_default_output_dir()), "/tmp/cccd_custom_output")

    def test_generate_service_template_documents_writes_the_right_count_and_fails_atomically(self):
        import tempfile

        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": "sim_replacement",
            "state": {**defaults, "document_type": ""},
        })))
        state = {**defaults, **response["state_patch"]}
        state["customer"] = {
            **state["customer"], "full_name": "NGUYỄN VĂN AN", "id_number": "001099999999",
            "issue_date": "01/01/2021", "issue_place": "Cục Cảnh sát QLHC về TTXH",
            "address": "1 Xã Đàn, Hà Nội",
        }
        state["subscribers"] = [{"subscriber_number": "0925123456", "monthly_fee": "", "activation_date": "19/08/2026", "sim_serial": "8984041234567890001", "commitment_note": ""}]
        state["backup_phone_1"] = "0901234567"
        state["shop_id_number"] = "0101234567"
        state["shop_issue_date"] = "01/01/2020"
        state["shop_issue_place"] = "Sở Tài chính Hà Nội"
        state["provider_representative"] = "LÊ THỊ ĐẠI DIỆN"

        def fake_convert(docx_paths, output_dir, dpi=150, filename_for=None):
            del dpi
            output_dir.mkdir(parents=True, exist_ok=True)
            outputs = []
            for docx_path in docx_paths:
                target = output_dir / filename_for(docx_path, 1)
                target.write_bytes(b"jpeg page")
                outputs.append(target)
            return outputs

        with tempfile.TemporaryDirectory() as folder, patch(
            "desktop_app.frontend.web_bridge.convert_docx_batch_to_images",
            side_effect=fake_convert,
        ):
            for number in (1, 2, 3):
                Path(folder, f"{number}.jpg").write_bytes(b"source")
            self.bridge._last_source_dir = folder
            result = self._run_generation("sim_replacement", state, folder)
            self.assertTrue(result["ok"], result)
            self.assertEqual(len(result["paths"]), 2)
            self.assertEqual(Path(result["paths"][0]).name, "7.jpg")
            self.assertEqual(Path(result["paths"][1]).name, "8.jpg")
            Path(folder, "9.jpg").write_bytes(b"stale generated page")
            repeated = self._run_generation("sim_replacement", state, folder)
            self.assertTrue(repeated["ok"], repeated)
            self.assertEqual(Path(repeated["paths"][0]).name, "7.jpg")
            self.assertEqual(Path(repeated["paths"][1]).name, "8.jpg")
            self.assertFalse(Path(folder, "9.jpg").exists())

            # If the filesystem fails while committing the new JPG set, the
            # previous complete result must be restored rather than leaving
            # a half-replaced dossier.
            old_page = Path(folder, "7.jpg")
            old_extra = Path(folder, "8.jpg")
            old_page.write_bytes(b"old page 7")
            old_extra.write_bytes(b"old page 8")
            with patch(
                "desktop_app.frontend.web_bridge.shutil.copy2",
                side_effect=OSError("simulated commit failure"),
            ):
                failed_commit = self._run_generation("sim_replacement", state, folder)
            self.assertFalse(failed_commit["ok"])
            self.assertEqual(old_page.read_bytes(), b"old page 7")
            self.assertEqual(old_extra.read_bytes(), b"old page 8")

        # Missing a required field -> fails, no output dict key with paths.
        state["customer"] = {**state["customer"], "full_name": ""}
        with tempfile.TemporaryDirectory() as folder:
            for number in (1, 2, 3):
                Path(folder, f"{number}.jpg").write_bytes(b"source")
            self.bridge._last_source_dir = folder
            result = self._run_generation("sim_replacement", state, folder)
            self.assertFalse(result["ok"])
            self.assertTrue(any(e["path"] == "customer.full_name" for e in result["errors"]))

    def test_prepaid_transfer_org_appends_the_business_certificate_pages(self):
        # PREPAID_TRANSFER_ORG (Mẫu 1) is the only mẫu that appends 2 extra
        # pages after its own generated documents -- the shop's own business
        # registration certificate, proving the signing representative's
        # authority (fig2.jpg is the certificate's own page 1, fig1.jpg its
        # page 2 -- see _PREPAID_TRANSFER_ORG_EXTRA_PAGES).
        import tempfile

        from desktop_app.backend.paths import resource_path

        self.bridge.company_profile = PersonData(
            entity_type="Tổ chức", organization_name="CÔNG TY CHỦ CŨ",
            business_registration_number="0101234567",
            business_registration_issue_date="01/01/2020",
            business_registration_issue_place="Sở Tài chính Hà Nội",
            headquarters_address="1 Xã Đàn",
        )
        self.bridge.representative_profile = PersonData(
            full_name="NGƯỜI ĐẠI DIỆN MẶC ĐỊNH", id_number="001090001234",
            issue_date="01/01/2022", issue_place="Cục Cảnh sát",
            date_of_birth="01/01/1990", nationality="Việt Nam", address="Hà Nội",
            representative_position="Giám đốc",
        )
        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": "prepaid_transfer_org",
            "state": {**defaults, "document_type": ""},
        })))
        state = {**defaults, **response["state_patch"]}
        state["new_owner"] = {
            **state["new_owner"], "full_name": "CHỦ MỚI TRONG ẢNH", "id_number": "001099999999",
            "issue_date": "01/01/2021", "issue_place": "Cục Cảnh sát", "date_of_birth": "01/01/1999",
            "nationality": "Việt Nam", "address": "Hà Nội",
        }
        state["subscribers"] = [{"subscriber_number": "0925123456", "monthly_fee": "", "activation_date": "19/08/2026", "sim_serial": "8984041234567890001", "commitment_note": ""}]
        state["service_point_address"] = state.get("service_point_address") or "1 Xã Đàn"
        state["service_point_phone"] = "0901234567"

        def fake_convert(docx_paths, output_dir, dpi=150, filename_for=None):
            del dpi
            output_dir.mkdir(parents=True, exist_ok=True)
            outputs = []
            for docx_path in docx_paths:
                target = output_dir / filename_for(docx_path, 1)
                target.write_bytes(b"jpeg page")
                outputs.append(target)
            return outputs

        with tempfile.TemporaryDirectory() as folder, patch(
            "desktop_app.frontend.web_bridge.convert_docx_batch_to_images",
            side_effect=fake_convert,
        ):
            for number in (1, 2, 3):
                Path(folder, f"{number}.jpg").write_bytes(b"source")
            self.bridge._last_source_dir = folder
            result = self._run_generation("prepaid_transfer_org", state, folder)
            self.assertTrue(result["ok"], result)
            # 4 documents (transfer/aftersale/beautiful_number/prepaid_contract)
            # + the 2 appended certificate pages.
            self.assertEqual(len(result["paths"]), 6)
            extra_page_2, extra_page_1 = result["paths"][-2:]
            self.assertEqual(
                Path(extra_page_2).read_bytes(),
                resource_path("desktop_app", "backend", "documents", "transfer", "fig2.jpg").read_bytes(),
            )
            self.assertEqual(
                Path(extra_page_1).read_bytes(),
                resource_path("desktop_app", "backend", "documents", "transfer", "fig1.jpg").read_bytes(),
            )

    def test_only_prepaid_transfer_org_gets_the_business_certificate_pages(self):
        import tempfile

        defaults = self.bridge._default_report_dict()
        response = json.loads(self.bridge.on_service_template_changed(json.dumps({
            "previous_service_template": "", "new_service_template": "sim_replacement",
            "state": {**defaults, "document_type": ""},
        })))
        state = {**defaults, **response["state_patch"]}
        state["customer"] = {
            **state["customer"], "full_name": "NGUYỄN VĂN AN", "id_number": "001099999999",
            "issue_date": "01/01/2021", "issue_place": "Cục Cảnh sát QLHC về TTXH",
            "address": "1 Xã Đàn, Hà Nội",
        }
        state["subscribers"] = [{"subscriber_number": "0925123456", "monthly_fee": "", "activation_date": "19/08/2026", "sim_serial": "8984041234567890001", "commitment_note": ""}]

        def fake_convert(docx_paths, output_dir, dpi=150, filename_for=None):
            del dpi
            output_dir.mkdir(parents=True, exist_ok=True)
            outputs = []
            for docx_path in docx_paths:
                target = output_dir / filename_for(docx_path, 1)
                target.write_bytes(b"jpeg page")
                outputs.append(target)
            return outputs

        with tempfile.TemporaryDirectory() as folder, patch(
            "desktop_app.frontend.web_bridge.convert_docx_batch_to_images",
            side_effect=fake_convert,
        ):
            for number in (1, 2, 3):
                Path(folder, f"{number}.jpg").write_bytes(b"source")
            self.bridge._last_source_dir = folder
            result = self._run_generation("sim_replacement", state, folder)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["paths"]), 2)


if __name__ == "__main__":
    unittest.main()
