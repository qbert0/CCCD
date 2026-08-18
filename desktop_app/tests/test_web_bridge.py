import json
import os
import unittest

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
        self.assertEqual(response["state_patch"]["provider_representative"], "LÊ THỊ ĐẠI DIỆN")

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


if __name__ == "__main__":
    unittest.main()
