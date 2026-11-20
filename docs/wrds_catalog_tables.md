# WRDS catalog: every readable table

Generated from the scan of 20 Nov 2026 described in [`wrds_catalog.md`](wrds_catalog.md); read that file first.
One row per table the login could `SELECT` from. `rows` is the planner's estimate (`pg_class.reltuples`), not a
count; `view` means the object stores no rows of its own. `dates` is the oldest and newest value of the column named,
asked only for tables under 5 million estimated rows; a date after the scan day is the vendor's own placeholder or a
fiscal period end. `empty` marks a table that returned no row. Column names and five sample rows per table are not
in this repository; they are in the scan output.

## aha_sample

| table | rows | columns | dates |
|---|---|---|---|
| `annual_survey` | 873 | 1105 | `dtbeg` 1987-09-09 to 2261-06-24 |
| `hcris` | 100 | 206 | `begdate` 2005-01-01 to 2023-01-01 |
| `it_survey` | 100 | 1126 | - |
| `summary_of_changes` | 10 | 18 | - |

## ahasamp

| table | rows | columns | dates |
|---|---|---|---|
| `annual_survey` | view | 1105 | `dtbeg` 1987-09-09 to 2261-06-24 |
| `hcris` | view | 206 | `begdate` 2005-01-01 to 2023-01-01 |
| `it_survey` | view | 1126 | - |
| `summary_of_changes` | view | 18 | - |

## altrata_exec_samp

| table | rows | columns | dates |
|---|---|---|---|
| `announce` | 17 | 9 | `announcement_date` 2025-07-08 to 2026-06-27 |
| `announce_role_title_category` | 25 | 6 | - |
| `announce_to_role_mapping` | 14 | 3 | - |
| `education` | 6,820 | 7 | `education_start_date` 1956-07-16 to 2020-07-16 |
| `external_identifier` | 8,032 | 4 | - |
| `family_office_per` | view (empty) | 5 | - |
| `membership` | 1,046 | 7 | `membership_start_date` 1970-01-16 to 2026-07-16 |
| `org` | 1 | 25 | `date_extinct`, not asked |
| `org_charitable_cause` | view (empty) | 2 | - |
| `org_charitable_donation` | 14 | 5 | `charitable_donation_date` 2001-07-16 to 2022-07-16 |
| `org_currency_metric` | 3 | 7 | `org_currency_metric_date` 2025-09-27 to 2025-09-27 |
| `org_financial` | 9 | 6 | `org_financial_measurement_date` 2025-09-27 to 2025-09-27 |
| `org_index` | 4 | 8 | `index_start_date` 2025-11-12 to 2025-11-12 |
| `org_insight` | 1 | 4 | - |
| `org_numeric_metric` | 1 | 6 | `org_numeric_metric_date` 2026-07-24 to 2026-07-24 |
| `per` | 3,744 | 21 | `date_of_birth` 1926-08-19 to 1997-07-20 |
| `per_address` | 1,232 | 6 | - |
| `per_board_metric` | 1,595 | 10 | - |
| `per_donation_summary` | 664 | 3 | - |
| `per_interest` | 2,626 | 7 | - |
| `per_net_worth_summary` | 1,089 | 7 | - |
| `per_org_summary` | 6,731 | 3 | - |
| `per_political_donation` | 9,313 | 7 | `political_donation_date` 1979-06-11 to 2025-08-26 |
| `per_relationship` | 342 | 6 | - |
| `per_wealth_profile` | 1,051 | 2 | - |
| `private_foundation` | 37 | 4 | - |
| `role` | 4,494 | 18 | `role_start_date` 1976-04-01 to 2026-07-16 |
| `role_title_category` | 4,755 | 7 | - |
| `wealth_asset` | 1,924 | 13 | - |
| `wrds_org_ids` | 1 | 4 | - |
| `wrds_org_networks` | 3,786 | 18 | `overlap_start_date` 1976-04-01 to 2026-07-16 |
| `wrds_org_summary` | 1 | 28 | - |
| `wrds_per_networks` | 8,001,660 | 17 | `overlap_start_date`, not asked (too big) |
| `wrds_per_summary` | 1,595 | 15 | - |
| `wrds_role` | 4,755 | 27 | `role_start_date` 1976-04-01 to 2026-07-16 |

## altsamp

| table | rows | columns | dates |
|---|---|---|---|
| `announce` | view | 9 | `announcement_date` 2025-07-08 to 2026-06-27 |
| `announce_role_title_category` | view | 6 | - |
| `announce_to_role_mapping` | view | 3 | - |
| `education` | view | 7 | `education_start_date` 1956-07-16 to 2020-07-16 |
| `external_identifier` | view | 4 | - |
| `family_office_per` | view (empty) | 5 | - |
| `membership` | view | 7 | `membership_start_date` 1970-01-16 to 2026-07-16 |
| `org` | view | 25 | `date_extinct`, not asked |
| `org_charitable_cause` | view (empty) | 2 | - |
| `org_charitable_donation` | view | 5 | `charitable_donation_date` 2001-07-16 to 2022-07-16 |
| `org_currency_metric` | view | 7 | `org_currency_metric_date` 2025-09-27 to 2025-09-27 |
| `org_financial` | view | 6 | `org_financial_measurement_date` 2025-09-27 to 2025-09-27 |
| `org_index` | view | 8 | `index_start_date` 2025-11-12 to 2025-11-12 |
| `org_insight` | view | 4 | - |
| `org_numeric_metric` | view | 6 | `org_numeric_metric_date` 2026-07-24 to 2026-07-24 |
| `per` | view | 21 | `date_of_birth` 1926-08-19 to 1997-07-20 |
| `per_address` | view | 6 | - |
| `per_board_metric` | view | 10 | - |
| `per_donation_summary` | view | 3 | - |
| `per_interest` | view | 7 | - |
| `per_net_worth_summary` | view | 7 | - |
| `per_org_summary` | view | 3 | - |
| `per_political_donation` | view | 7 | `political_donation_date` 1979-06-11 to 2025-08-26 |
| `per_relationship` | view | 6 | - |
| `per_wealth_profile` | view | 2 | - |
| `private_foundation` | view | 4 | - |
| `role` | view | 18 | `role_start_date` 1976-04-01 to 2026-07-16 |
| `role_title_category` | view | 7 | - |
| `wealth_asset` | view | 13 | - |
| `wrds_org_ids` | view | 4 | - |
| `wrds_org_networks` | view | 18 | `overlap_start_date` 1976-04-01 to 2026-07-16 |
| `wrds_org_summary` | view | 28 | - |
| `wrds_per_networks` | view | 17 | `overlap_start_date` 1944-07-16 to 2026-07-24 |
| `wrds_per_summary` | view | 15 | - |
| `wrds_role` | view | 27 | `role_start_date` 1976-04-01 to 2026-07-16 |

## audit

| table | rows | columns | dates |
|---|---|---|---|
| `f01_auditor_affiliate` | view | 11 | `create_date` 2006-02-14 to 2026-08-04 |
| `f01_auditor_event` | view | 3 | `event_date` 1997-01-01 to 2026-09-08 |
| `f01_auditor_event_to_auditor` | view | 6 | - |
| `f01_auditor_event_type` | view | 2 | - |
| `f01_auditor_location` | view | 12 | - |
| `f01_deleted_keys` | view | 1 | - |
| `f01_sec_locations` | view | 6 | - |
| `f02_deleted_keys` | view | 1 | - |
| `f03_deleted_keys` | view | 1 | - |
| `f04_deleted_keys` | view | 1 | - |
| `f06_deleted_keys` | view | 1 | - |
| `f06_form_ap_divided` | view (empty) | 12 | - |
| `f06_form_ap_filing` | view | 26 | `audit_report_date` 2016-06-27 to 2026-08-25 |
| `f06_form_ap_not_divided` | view | 11 | - |
| `f10_deleted_keys` | view | 1 | - |
| `f10_ic_dis_con_qua` | view | 3 | - |
| `f10_ic_dis_con_rea` | view | 3 | - |
| `f10_ic_qualifier` | view | 3 | - |
| `f10_ic_reason` | view | 3 | - |
| `f11_deleted_keys` | view | 1 | - |
| `f11_ic_opinion_qualifier` | view | 3 | - |
| `f11_ic_opinion_reason` | view | 3 | - |
| `f11_ic_qualifier` | view | 3 | - |
| `f11_ic_reason` | view | 3 | - |
| `f16_deleted_keys` | view | 1 | - |
| `f17_deleted_keys` | view | 1 | - |
| `f17_dno_change` | view | 15 | `file_date` 2000-01-04 to 2026-09-24 |
| `f20_deleted_keys` | view | 1 | - |
| `f20_nt_fil_not_to_rea` | view | 5 | `create_date` 2005-10-12 to 2026-09-25 |
| `f20_nt_filer_reason` | view | 5 | `create_date` 2005-10-11 to 2019-04-02 |
| `f27_auditor` | view | 11 | - |
| `f27_corporate_position` | view | 5 | `create_date` 2008-07-03 to 2026-09-25 |
| `f27_document_detail` | view | 18 | `accepted` 1995-09-28 to 2026-09-23 |
| `f27_document_detail_files` | view | 10 | `create_date` 2009-02-03 to 2026-09-24 |
| `f27_person` | view | 9 | `create_date` 2008-07-11 to 2026-09-10 |
| `f27_person_filing` | view | 7 | `create_date` 2009-01-29 to 2026-09-10 |
| `f27_person_positions` | view | 5 | `create_date` 2009-01-29 to 2026-09-10 |
| `f27_sec_locations` | view | 5 | - |
| `f28_auditor` | view | 11 | - |
| `f28_foundation_codes` | view | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f28_ntee_codes` | view | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f28_ntee_common_codes` | view | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f28_sub_cla_cod` | view | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f29_auditor` | view | 11 | - |
| `f29_corporate_position` | view | 5 | `create_date` 2008-07-03 to 2026-09-25 |
| `f29_document_detail` | view | 18 | `accepted` 1995-09-28 to 2026-09-23 |
| `f29_document_detail_files` | view | 10 | `create_date` 2009-02-03 to 2026-09-24 |
| `f29_person` | view | 9 | `create_date` 2008-07-17 to 2026-09-10 |
| `f29_person_filing` | view | 7 | `create_date` 2009-02-03 to 2026-09-10 |
| `f29_person_positions` | view | 5 | `create_date` 2009-02-03 to 2026-09-10 |
| `f29_sec_locations` | view | 5 | - |
| `f30_auditor` | view | 11 | - |
| `f30_foundation_codes` | view | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f30_ntee_codes` | view | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f30_ntee_common_codes` | view | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f30_sub_cla_cod` | view | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f34_aud_opi_to_goi_con_iss` | view | 5 | `create_date` 2009-08-20 to 2022-03-14 |
| `f34_deleted_keys` | view | 1 | - |
| `f34_form_ap_divided` | view | 12 | - |
| `f34_form_ap_filing` | view | 26 | `audit_report_date` 2014-02-12 to 2026-09-23 |
| `f34_form_ap_not_divided` | view | 11 | - |
| `f34_going_concern_issues` | view | 4 | `create_date` 2009-08-20 to 2021-03-22 |
| `f35_deleted_keys` | view | 1 | - |
| `f35_ria_adv_sa_direct_owners` | view | 15 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sb_indirect_owners` | view | 16 | `create_date` 2010-10-20 to 2026-09-25 |
| `f35_ria_adv_sd_10_con_per` | view | 18 | `effective_date` 1914-07-14 to 2066-12-05 |
| `f35_ria_adv_sd_1b_other_names` | view | 6 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_1f_other_offices` | view | 13 | `create_date` 2010-10-20 to 2026-09-25 |
| `f35_ria_adv_sd_1i_www_addresses` | view | 5 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_1k_books_records` | view | 16 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_1l_for_reg` | view | 7 | `create_date` 2011-02-19 to 2026-09-25 |
| `f35_ria_adv_sd_2a1_sec_exe_ord` | view | 6 | `order_date` 1997-07-08 to 2021-06-11 |
| `f35_ria_adv_sd_2a7_aff_adv` | view | 7 | `create_date` 2010-03-11 to 2012-11-05 |
| `f35_ria_adv_sd_2a8_new_for_adv` | view | 6 | `create_date` 2010-03-11 to 2026-09-25 |
| `f35_ria_adv_sd_2a9_mul_adv` | view | 7 | `create_date` 2010-03-11 to 2026-09-24 |
| `f35_ria_adv_sd_4_successions` | view | 7 | `create_date` 2011-03-08 to 2026-09-10 |
| `f35_ria_adv_sd_7a_aff_adv_dea` | view | 9 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_7b_lim_par` | view | 11 | `create_date` 2010-10-20 to 2015-02-02 |
| `f35_ria_adv_sd_9c_accountant` | view | 19 | `create_date` 2011-02-23 to 2026-09-25 |
| `f35_ria_adv_sd_miscellaneous` | view | 5 | `create_date` 2010-03-11 to 2026-09-25 |
| `f35_ria_form_url_to_live` | view | 5 | `date_submitted` 2007-04-26 to 2026-09-23 |
| `f35_ria_sd9_acc_to_aud` | view | 7 | `create_date` 2011-02-24 to 2026-09-26 |
| `f35_ria_sd_5g3_public_funds` | view | 13 | - |
| `f35_ria_sd_7b_admin` | view | 21 | - |
| `f35_ria_sd_7b_auditor` | view | 21 | - |
| `f35_ria_sd_7b_custodian` | view | 17 | - |
| `f35_ria_sd_7b_feeder_fund` | view | 10 | - |
| `f35_ria_sd_7b_marketer` | view | 16 | - |
| `f35_ria_sd_7b_prime_broker` | view | 16 | - |
| `f35_ria_sd_7b_private_funds` | view | 39 | - |
| `f36_deleted_keys` | view | 1 | - |
| `f36_ria_adv_sa_direct_owners` | view | 15 | `create_date` 2010-10-19 to 2026-09-25 |
| `f36_ria_adv_sb_indirect_owners` | view | 16 | `create_date` 2011-02-19 to 2026-09-25 |
| `f36_ria_adv_sd_10_con_per` | view | 18 | `effective_date` 1914-07-14 to 2026-12-12 |
| `f36_ria_adv_sd_1b_other_names` | view | 6 | `create_date` 2011-02-21 to 2026-09-25 |
| `f36_ria_adv_sd_1f_other_offices` | view | 13 | `create_date` 2010-10-21 to 2026-09-25 |
| `f36_ria_adv_sd_1i_www_addresses` | view | 5 | `create_date` 2010-10-19 to 2026-09-25 |
| `f36_ria_adv_sd_1k_books_records` | view | 16 | `create_date` 2010-10-20 to 2026-09-25 |
| `f36_ria_adv_sd_1l_for_reg` | view | 7 | `create_date` 2011-02-21 to 2026-09-25 |
| `f36_ria_adv_sd_2a1_sec_exe_ord` | view | 6 | `order_date` 1997-07-08 to 1998-01-16 |
| `f36_ria_adv_sd_2a7_aff_adv` | view | 7 | `create_date` 2010-03-11 to 2012-09-10 |
| `f36_ria_adv_sd_2a8_new_for_adv` | view | 6 | `create_date` 2010-03-11 to 2026-09-25 |
| `f36_ria_adv_sd_2a9_mul_adv` | view | 7 | `create_date` 2010-03-11 to 2026-09-24 |
| `f36_ria_adv_sd_4_successions` | view | 7 | `create_date` 2012-07-12 to 2026-09-10 |
| `f36_ria_adv_sd_7a_aff_adv_dea` | view | 9 | `create_date` 2010-10-19 to 2026-09-25 |
| `f36_ria_adv_sd_7b_lim_par` | view | 11 | `create_date` 2010-10-21 to 2015-02-02 |
| `f36_ria_adv_sd_9c_accountant` | view | 19 | `create_date` 2011-03-14 to 2026-09-25 |
| `f36_ria_adv_sd_miscellaneous` | view | 5 | `create_date` 2010-03-11 to 2026-09-25 |
| `f36_ria_form_url_to_live` | view | 5 | `date_submitted` 2007-04-26 to 2026-09-23 |
| `f36_ria_sd9_acc_to_aud` | view | 7 | `create_date` 2011-03-15 to 2026-09-26 |
| `f36_ria_sd_5g3_public_funds` | view | 13 | - |
| `f36_ria_sd_7b_admin` | view | 21 | - |
| `f36_ria_sd_7b_auditor` | view | 21 | - |
| `f36_ria_sd_7b_custodian` | view | 17 | - |
| `f36_ria_sd_7b_feeder_fund` | view | 10 | - |
| `f36_ria_sd_7b_marketer` | view | 16 | - |
| `f36_ria_sd_7b_prime_broker` | view | 16 | - |
| `f36_ria_sd_7b_private_funds` | view | 39 | - |
| `f39_res_aud_beg_end` | view | 5 | - |
| `f39_restatement_auditor_period` | view | 3 | - |
| `f39_restatement_category` | view | 3 | - |
| `f39_restatement_filings` | view | 31 | `file_date` 1995-03-29 to 2026-09-23 |
| `f39_restatement_fiscal_year_ends` | view | 5 | - |
| `f39_restatement_periods` | view | 21 | - |
| `f39_restatement_to_category` | view | 3 | - |
| `f39_restatement_type` | view | 5 | `create_date` 2011-08-11 to 2011-08-11 |
| `f43_admin` | view | 8 | - |
| `f43_broker` | view | 11 | - |
| `f43_fund_to_auditor` | view | 12 | - |
| `f53_auditor` | view | 11 | - |
| `f53_ins_assets` | view | 11 | - |
| `f53_ins_contacts_demographics` | view | 16 | - |
| `f53_ins_demographics` | view | 26 | - |
| `f53_ins_demographics_expanded` | view | 35 | - |
| `f53_ins_expenses` | view | 7 | - |
| `f53_ins_form_to_auditor_info` | view | 3 | - |
| `f53_ins_form_to_company` | view | 3 | - |
| `f53_ins_gen_int_bas` | view | 20 | `date_response` 1899-12-31 to 9999-12-31 |
| `f53_ins_revenue` | view | 9 | - |
| `f56_acc_est_cha_fil` | view | 6 | `file_date` 2000-01-03 to 2026-09-24 |
| `f56_acc_est_tax` | view | 4 | - |
| `f56_acc_est_to_tax` | view | 3 | - |
| `f72_int_audit_opinion_auditor` | view | 21 | `opinion_fiscal_year_end` 2010-01-02 to 2026-06-30 |
| `f72_int_audit_opinion_partner` | view | 23 | `opinion_fiscal_year_end` 2010-01-02 to 2026-06-30 |
| `f74_aqrm_company_flags` | view | 4 | - |
| `f74_fee_sup_acc_est_cha` | view | 4 | - |
| `f74_fee_sup_aud_cha` | view | 4 | - |
| `f74_fee_sup_aud_fee_out` | view | 5 | - |
| `f74_fee_sup_aud_rat` | view | 4 | - |
| `f74_fee_sup_civ_rig_lit` | view | 4 | - |
| `f74_fee_sup_dis_com` | view | 14 | `file_date` 2011-01-06 to 2026-09-25 |
| `f74_fee_sup_dis_con` | view | 4 | - |
| `f74_fee_sup_emp_lab_lit` | view | 4 | - |
| `f74_fee_sup_eng_par_cha` | view | 4 | - |
| `f74_fee_sup_env_lit` | view | 4 | - |
| `f74_fee_sup_fin_res` | view | 4 | - |
| `f74_fee_sup_ill_act_lit` | view | 4 | - |
| `f74_fee_sup_int_con` | view | 4 | - |
| `f74_fee_sup_int_pro_lit` | view | 4 | - |
| `f74_fee_sup_mat_imp` | view | 4 | - |
| `f74_fee_sup_non_aud_fee` | view | 5 | - |
| `f74_fee_sup_per_adj` | view | 4 | - |
| `f74_fee_sup_ple_sec` | view | 4 | - |
| `f74_fee_sup_reg_lit` | view | 4 | - |
| `f74_fee_sup_sha_act` | view | 4 | - |
| `f74_fee_sup_sha_act_lit` | view | 4 | - |
| `f74_feed_support74_altman_score` | view | 4 | - |
| `f74_feed_support74_audit_fees` | view | 15 | `file_date` 2000-03-27 to 2026-09-24 |
| `f74_feed_support74_beneish_score` | view | 9 | `file_date` 2009-08-21 to 2026-09-25 |
| `f74_feed_support74_benfords_law` | view | 32 | `file_date` 2009-05-29 to 2026-09-25 |
| `f74_feed_support74_ceo_change` | view | 4 | - |
| `f74_feed_support74_cfo_change` | view | 4 | - |
| `f74_feed_support74_cybersecurity` | view | 4 | - |
| `f74_feed_support74_going_concern` | view | 4 | - |
| `f74_feed_support74_late_filings` | view | 4 | - |
| `f78_feed_support78_cam_topic` | view | 2 | - |
| `f79_int_res_iss_tax` | view | 3 | - |
| `f79_int_res_iss_to_cat` | view | 3 | - |
| `f79_int_restatement_filing` | view | 8 | `file_date` 2012-01-26 to 2026-09-14 |
| `f79_int_restatement_to_issues` | view | 2 | - |
| `f79_int_restatement_type` | view | 2 | - |
| `f85_cyb_bre_to_inf` | view | 3 | - |
| `f85_cybersec_breach_attack` | view | 2 | - |
| `f85_cybersec_breach_information` | view | 2 | - |
| `f85_cybersec_breach_to_attack` | view | 3 | - |
| `f85_cybersec_filing` | view | 7 | `disclosure_date` 2004-06-23 to 2026-09-23 |
| `f85_cybersec_target_` | view | 5 | - |
| `f85_cybersec_target_relationship` | view | 2 | - |
| `f89_inspection_date` | view | 3 | - |
| `f89_issue_taxonomy_to_group` | view | 4 | - |
| `f89_office_location` | view | 4 | - |
| `f89_taxonomy` | view | 2 | - |
| `f89_taxonomy_group` | view | 2 | - |
| `f90_fee_aud_opi_not_unq` | view | 4 | - |
| `f90_feed90_audit_fee_outlier` | view | 6 | - |
| `f90_feed90_audit_fees` | view | 7 | - |
| `f90_feed90_auditor_change` | view | 4 | - |
| `f90_feed90_company_flag` | view | 15 | `opinion_signature_date` 2010-02-08 to 2026-08-18 |
| `f90_feed90_financial_restatement` | view | 4 | - |
| `f90_feed90_going_concern` | view | 4 | - |
| `f90_feed90_non_audit_fees` | view | 4 | - |
| `f91_fee_ord_rei_det` | view | 4 | - |
| `f91_feed91_all_related_release` | view | 6 | `release_date` 1999-10-18 to 2026-09-11 |
| `f91_feed91_order_bar_detail` | view | 6 | - |
| `f91_feed91_related_party` | view | 13 | - |
| `f91_feed91_release_to_issue` | view | 4 | - |
| `f91_feed91_respondent` | view | 14 | - |
| `f91_feed91_respondent_order` | view | 6 | - |
| `f91_feed91_summary_text` | view | 3 | - |
| `feed01_auditors` | view | 15 | - |
| `feed02_auditor_changes` | view | 243 | `dismiss_date` 1987-01-01 to 2027-08-06 |
| `feed03_audit_fees` | view | 215 | `fiscal_year_ended` 1996-09-30 to 2026-07-31 |
| `feed04_audit_fees_restated` | view | 215 | `fiscal_year_ended` 1996-09-30 to 2026-07-31 |
| `feed06_benefit_plan_opinions` | view | 215 | `sig_date_of_opin` 1997-07-14 to 2026-09-24 |
| `feed07_current_auditor` | view | 5 | - |
| `feed08_auditor_during` | view | 6 | `event_date` 1880-12-31 to 2026-09-25 |
| `feed10_sox_302_disclosure_contro` | view | 215 | `period_end_date_num` 1986-03-31 to 2026-08-31 |
| `feed11_sox_404_internal_controls` | view | 240 | `fye_ic_op` 2000-03-31 to 2026-08-02 |
| `feed12_company_block` | view | 253 | `name_change_date1` 1994-01-05 to 2026-09-25 |
| `feed16_accelerated_filer` | view | 208 | `pe_date` 1986-03-31 to 2026-12-31 |
| `feed17_director_and_officer_chan` | view | 237 | `eff_date` 1999-03-12 to 2028-12-31 |
| `feed20_nt` | view | 219 | `pe_date_num` 1993-10-31 to 2026-12-31 |
| `feed27_broker_dealer_focus_repor` | view | 72 | `period_ended_date` 2000-05-31 to 2026-07-03 |
| `feed28_non_profit_single_audit` | view | 100 | `fy_end_date` 1997-05-31 to 2026-06-30 |
| `feed29_current_broker_dealer_foc` | view | 60 | `period_ended_date` 2000-12-31 to 2026-07-03 |
| `feed30_current_non_profit_single` | view | 100 | `fy_end_date` 1997-06-30 to 2026-06-30 |
| `feed33_erisa` | view | 541 | `form_plan_year_begin_date` 1899-03-21 to 9910-08-12 |
| `feed34_revised_audit_opinions` | view | 223 | `sig_date_of_op` 1996-02-05 to 2026-12-16 |
| `feed35_ria` | view | 174 | `sig_pag_dom_sig_date` 1911-07-11 to 2026-09-25 |
| `feed36_ria_current_engagements` | view | 174 | `sig_pag_dom_sig_date` 1924-05-05 to 2026-09-25 |
| `feed39_financial_restatements` | view | 249 | `res_begin_date` 1983-03-26 to 2026-04-01 |
| `feed43_private_fund` | view | 35 | - |
| `feed53_naic` | view | 212 | `pcaob_reg_date` 2003-08-18 to 2023-10-22 |
| `feed55_auditor_ratification` | view | 208 | `file_date` 2010-03-01 to 2026-09-23 |
| `feed56_accounting_estimates_chan` | view | 213 | `effective_date` 1999-01-01 to 2026-08-01 |
| `feed59_bank_holding_company` | view | 356 | `date_insured`, not asked |
| `feed65_impairments` | view | 221 | `period_end_date` 2005-10-31 to 2026-08-01 |
| `feed70_europe_company_block` | view | 66 | `ipo_date` 1900-01-01 to 2026-07-03 |
| `feed71_europe_audit_fee` | view | 47 | `source_filing_fiscal_year_end` 2008-02-29 to 2026-07-31 |
| `feed72_europe_audit_opinion` | view | 27 | `source_filing_fiscal_year_end` 2010-01-01 to 2026-06-30 |
| `feed73_europe_auditor_engagement` | view | 14 | `auditor_since_date` 1920-01-01 to 2026-09-25 |
| `feed74_aqrm` | view | 36 | `opinion_file_date` 2000-01-03 to 2026-09-24 |
| `feed75_europe_auditor_changes` | view | 28 | `dismissed_announced_date` 2009-09-23 to 2026-09-21 |
| `feed76_transparency_reports` | view | 21 | `market_cap_as_of_date` 2009-03-31 to 2026-09-21 |
| `feed77_europe_key_audit_matters` | view | 9 | - |
| `feed78_critical_audit_matters` | view | 10 | - |
| `feed79_europe_restatements` | view | 36 | `fiscal_year_end` 2010-12-31 to 2026-06-30 |
| `feed85_cybersecurity` | view | 78 | `breach_disclosure_date` 2004-06-23 to 2026-09-23 |
| `feed86_audit_firm_events` | view | 27 | `event_date` 1997-01-01 to 2026-09-08 |
| `feed89_pcaob_report` | view | 32 | `issuance_date` 2004-08-26 to 2026-09-01 |
| `feed90_europe_aqrm` | view | 8 | `opinion_signature_date` 2010-02-08 to 2026-08-18 |
| `feed91_aaer` | view | 19 | `first_release_date` 1999-10-18 to 2026-09-11 |
| `wrds_lookup_auditors` | view | 3 | - |
| `wrds_lookup_bank_holding` | view | 3 | - |
| `wrds_lookup_edgar_company_block` | view | 5 | - |
| `wrds_lookup_europe` | view | 6 | - |
| `wrds_lookup_naic` | view | 5 | - |
| `wrds_lookup_non_profit_28` | view | 2 | - |
| `wrds_lookup_non_profit_30` | view | 2 | - |
| `wrds_lookup_private_fund` | view | 2 | - |

## audit_acct_os

| table | rows | columns | dates |
|---|---|---|---|
| `f56_acc_est_cha_fil` | 24,289 | 6 | `file_date` 2000-01-03 to 2026-09-24 |
| `f56_acc_est_tax` | 40 | 4 | - |
| `f56_acc_est_to_tax` | 19,860 | 3 | - |
| `f74_aqrm_company_flags` | 720,295 | 4 | - |
| `f74_fee_sup_acc_est_cha` | 14,827 | 4 | - |
| `f74_fee_sup_aud_cha` | 34,893 | 4 | - |
| `f74_fee_sup_aud_fee_out` | 56,974 | 5 | - |
| `f74_fee_sup_aud_rat` | 69,637 | 4 | - |
| `f74_fee_sup_civ_rig_lit` | 2,029 | 4 | - |
| `f74_fee_sup_dis_com` | 103,550 | 14 | `file_date` 2011-01-06 to 2026-09-25 |
| `f74_fee_sup_dis_con` | 779,557 | 4 | - |
| `f74_fee_sup_emp_lab_lit` | 12,139 | 4 | - |
| `f74_fee_sup_eng_par_cha` | 11,322 | 4 | - |
| `f74_fee_sup_env_lit` | 9,323 | 4 | - |
| `f74_fee_sup_fin_res` | 25,255 | 4 | - |
| `f74_fee_sup_ill_act_lit` | 18,444 | 4 | - |
| `f74_fee_sup_int_con` | 244,961 | 4 | - |
| `f74_fee_sup_int_pro_lit` | 43,261 | 4 | - |
| `f74_fee_sup_mat_imp` | 51,284 | 4 | - |
| `f74_fee_sup_non_aud_fee` | 29,383 | 5 | - |
| `f74_fee_sup_per_adj` | 3,943 | 4 | - |
| `f74_fee_sup_ple_sec` | 23,094 | 4 | - |
| `f74_fee_sup_reg_lit` | 5,332 | 4 | - |
| `f74_fee_sup_sha_act` | 157,380 | 4 | - |
| `f74_fee_sup_sha_act_lit` | 79,437 | 4 | - |
| `f74_feed_support74_altman_score` | 82,978 | 4 | - |
| `f74_feed_support74_audit_fees` | 193,344 | 15 | `file_date` 2000-03-27 to 2026-09-24 |
| `f74_feed_support74_beneish_score` | 40,131 | 9 | `file_date` 2009-08-21 to 2026-09-25 |
| `f74_feed_support74_benfords_law` | 107,150 | 32 | `file_date` 2009-05-29 to 2026-09-25 |
| `f74_feed_support74_ceo_change` | 51,762 | 4 | - |
| `f74_feed_support74_cfo_change` | 59,045 | 4 | - |
| `f74_feed_support74_cybersecurity` | 1,536 | 4 | - |
| `f74_feed_support74_going_concern` | 549,863 | 4 | - |
| `f74_feed_support74_late_filings` | 112,022 | 4 | - |
| `f78_feed_support78_cam_topic` | 61 | 2 | - |
| `f85_cyb_bre_to_inf` | 3,918 | 3 | - |
| `f85_cybersec_breach_attack` | 7 | 2 | - |
| `f85_cybersec_breach_information` | 13 | 2 | - |
| `f85_cybersec_breach_to_attack` | 1,549 | 3 | - |
| `f85_cybersec_filing` | 5,618 | 7 | `disclosure_date` 2004-06-23 to 2026-09-23 |
| `f85_cybersec_target_` | 1,640 | 5 | - |
| `f85_cybersec_target_relationship` | 2 | 2 | - |
| `f89_inspection_date` | 4,601 | 3 | - |
| `f89_issue_taxonomy_to_group` | 27,187 | 4 | - |
| `f89_office_location` | 9,676 | 4 | - |
| `f89_taxonomy` | 222 | 2 | - |
| `f89_taxonomy_group` | 8 | 2 | - |
| `f91_fee_ord_rei_det` | 150 | 4 | - |
| `f91_feed91_all_related_release` | 3,295 | 6 | `release_date` 1999-10-18 to 2026-09-11 |
| `f91_feed91_order_bar_detail` | 1,817 | 6 | - |
| `f91_feed91_related_party` | 4,968 | 13 | - |
| `f91_feed91_release_to_issue` | 7,824 | 4 | - |
| `f91_feed91_respondent` | 5,647 | 14 | - |
| `f91_feed91_respondent_order` | 7,542 | 6 | - |
| `f91_feed91_summary_text` | 3,295 | 3 | - |
| `feed55_auditor_ratification` | 70,563 | 208 | `file_date` 2010-03-01 to 2026-09-23 |
| `feed56_accounting_estimates_chan` | 15,511 | 213 | `effective_date` 1999-01-01 to 2026-08-01 |
| `feed65_impairments` | 43,220 | 221 | `period_end_date` 2005-10-31 to 2026-08-01 |
| `feed74_aqrm` | 302,461 | 36 | `opinion_file_date` 2000-01-03 to 2026-09-24 |
| `feed78_critical_audit_matters` | 53,888 | 10 | - |
| `feed85_cybersecurity` | 1,535 | 78 | `breach_disclosure_date` 2004-06-23 to 2026-09-23 |
| `feed86_audit_firm_events` | 10,498 | 27 | `event_date` 1997-01-01 to 2026-09-08 |
| `feed89_pcaob_report` | 4,333 | 32 | `issuance_date` 2004-08-26 to 2026-09-01 |
| `feed91_aaer` | 1,454 | 19 | `first_release_date` 1999-10-18 to 2026-09-11 |

## audit_audit_comp

| table | rows | columns | dates |
|---|---|---|---|
| `f01_auditor_affiliate` | 835 | 11 | `create_date` 2006-02-14 to 2026-08-04 |
| `f01_auditor_event` | 10,531 | 3 | `event_date` 1997-01-01 to 2026-09-08 |
| `f01_auditor_event_to_auditor` | 10,529 | 6 | - |
| `f01_auditor_event_type` | 4 | 2 | - |
| `f01_auditor_location` | 46,271 | 12 | - |
| `f01_deleted_keys` | 1,417 | 1 | - |
| `f01_sec_locations` | 327 | 6 | - |
| `f02_deleted_keys` | 1,126 | 1 | - |
| `f03_deleted_keys` | 12,646 | 1 | - |
| `f04_deleted_keys` | 12,646 | 1 | - |
| `f06_deleted_keys` | 145 | 1 | - |
| `f06_form_ap_divided` | view (empty) | 12 | - |
| `f06_form_ap_filing` | 10,064 | 26 | `audit_report_date` 2016-06-27 to 2026-08-25 |
| `f06_form_ap_not_divided` | 112 | 11 | - |
| `f10_deleted_keys` | 7,781 | 1 | - |
| `f10_ic_dis_con_qua` | 336,122 | 3 | - |
| `f10_ic_dis_con_rea` | 801,713 | 3 | - |
| `f10_ic_qualifier` | 5 | 3 | - |
| `f10_ic_reason` | 91 | 3 | - |
| `f11_deleted_keys` | 4,811 | 1 | - |
| `f11_ic_opinion_qualifier` | 175,062 | 3 | - |
| `f11_ic_opinion_reason` | 299,766 | 3 | - |
| `f11_ic_qualifier` | 5 | 3 | - |
| `f11_ic_reason` | 91 | 3 | - |
| `f16_deleted_keys` | 3,053 | 1 | - |
| `f17_deleted_keys` | 10,326 | 1 | - |
| `f17_dno_change` | 257,711 | 15 | `file_date` 2000-01-04 to 2026-09-24 |
| `f20_deleted_keys` | 263 | 1 | - |
| `f20_nt_fil_not_to_rea` | 179,156 | 5 | `create_date` 2005-10-12 to 2026-09-25 |
| `f20_nt_filer_reason` | 66 | 5 | `create_date` 2005-10-11 to 2019-04-02 |
| `f34_aud_opi_to_goi_con_iss` | 200,270 | 5 | `create_date` 2009-08-20 to 2022-03-14 |
| `f34_deleted_keys` | 52,588 | 1 | - |
| `f34_form_ap_divided` | 358 | 12 | - |
| `f34_form_ap_filing` | 176,045 | 26 | `audit_report_date` 2014-02-12 to 2026-09-23 |
| `f34_form_ap_not_divided` | 22,520 | 11 | - |
| `f34_going_concern_issues` | 58 | 4 | `create_date` 2009-08-20 to 2021-03-22 |
| `f39_res_aud_beg_end` | 29,198 | 5 | - |
| `f39_restatement_auditor_period` | 34,419 | 3 | - |
| `f39_restatement_category` | 69 | 3 | - |
| `f39_restatement_filings` | 83,517 | 31 | `file_date` 1995-03-29 to 2026-09-23 |
| `f39_restatement_fiscal_year_ends` | 15,842 | 5 | - |
| `f39_restatement_periods` | 85,497 | 21 | - |
| `f39_restatement_to_category` | 64,648 | 3 | - |
| `f39_restatement_type` | 4 | 5 | `create_date` 2011-08-11 to 2011-08-11 |
| `feed01_auditors` | 34,035 | 15 | - |
| `feed02_auditor_changes` | 37,024 | 243 | `dismiss_date` 1987-01-01 to 2027-08-06 |
| `feed03_audit_fees` | 295,314 | 215 | `fiscal_year_ended` 1996-09-30 to 2026-07-31 |
| `feed04_audit_fees_restated` | 295,314 | 215 | `fiscal_year_ended` 1996-09-30 to 2026-07-31 |
| `feed06_benefit_plan_opinions` | 39,539 | 215 | `sig_date_of_opin` 1997-07-14 to 2026-09-24 |
| `feed07_current_auditor` | 72,788 | 5 | - |
| `feed08_auditor_during` | 522,282 | 6 | `event_date` 1880-12-31 to 2026-09-25 |
| `feed10_sox_302_disclosure_contro` | 779,557 | 215 | `period_end_date_num` 1986-03-31 to 2026-08-31 |
| `feed11_sox_404_internal_controls` | 244,948 | 240 | `fye_ic_op` 2000-03-31 to 2026-08-02 |
| `feed16_accelerated_filer` | 824,174 | 208 | `pe_date` 1986-03-31 to 2026-12-31 |
| `feed17_director_and_officer_chan` | 579,845 | 237 | `eff_date` 1999-03-12 to 2028-12-31 |
| `feed20_nt` | 126,140 | 219 | `pe_date_num` 1993-10-31 to 2026-12-31 |
| `feed34_revised_audit_opinions` | 549,863 | 223 | `sig_date_of_op` 1996-02-05 to 2026-12-16 |
| `feed39_financial_restatements` | 29,198 | 249 | `res_begin_date` 1983-03-26 to 2026-04-01 |
| `wrds_lookup_auditors` | 34,785 | 3 | - |

## audit_common

| table | rows | columns | dates |
|---|---|---|---|
| `feed12_company_block` | 492,934 | 253 | `name_change_date1` 1994-01-05 to 2026-09-25 |
| `wrds_lookup_edgar_company_block` | 492,934 | 5 | - |

## audit_europe

| table | rows | columns | dates |
|---|---|---|---|
| `f72_int_audit_opinion_auditor` | 102,585 | 21 | `opinion_fiscal_year_end` 2010-01-02 to 2026-06-30 |
| `f72_int_audit_opinion_partner` | 122,641 | 23 | `opinion_fiscal_year_end` 2010-01-02 to 2026-06-30 |
| `f79_int_res_iss_tax` | 275 | 3 | - |
| `f79_int_res_iss_to_cat` | 163 | 3 | - |
| `f79_int_restatement_filing` | 5,289 | 8 | `file_date` 2012-01-26 to 2026-09-14 |
| `f79_int_restatement_to_issues` | 6,495 | 2 | - |
| `f79_int_restatement_type` | 2 | 2 | - |
| `f90_fee_aud_opi_not_unq` | 2,228 | 4 | - |
| `f90_feed90_audit_fee_outlier` | 16,663 | 6 | - |
| `f90_feed90_audit_fees` | 18,823 | 7 | - |
| `f90_feed90_auditor_change` | 9,359 | 4 | - |
| `f90_feed90_company_flag` | 60,847 | 15 | `opinion_signature_date` 2010-02-08 to 2026-08-18 |
| `f90_feed90_financial_restatement` | 2,523 | 4 | - |
| `f90_feed90_going_concern` | 6,889 | 4 | - |
| `f90_feed90_non_audit_fees` | 55,653 | 4 | - |
| `feed70_europe_company_block` | 52,284 | 66 | `ipo_date` 1900-01-01 to 2026-07-03 |
| `feed71_europe_audit_fee` | 128,254 | 47 | `source_filing_fiscal_year_end` 2008-02-29 to 2026-07-31 |
| `feed72_europe_audit_opinion` | 94,929 | 27 | `source_filing_fiscal_year_end` 2010-01-01 to 2026-06-30 |
| `feed73_europe_auditor_engagement` | 8,761 | 14 | `auditor_since_date` 1920-01-01 to 2026-09-25 |
| `feed75_europe_auditor_changes` | 9,359 | 28 | `dismissed_announced_date` 2009-09-23 to 2026-09-21 |
| `feed76_transparency_reports` | 266,793 | 21 | `market_cap_as_of_date` 2009-03-31 to 2026-09-21 |
| `feed77_europe_key_audit_matters` | 96,571 | 9 | - |
| `feed79_europe_restatements` | 2,523 | 36 | `fiscal_year_end` 2010-12-31 to 2026-06-30 |
| `feed90_europe_aqrm` | 87,611 | 8 | `opinion_signature_date` 2010-02-08 to 2026-08-18 |
| `wrds_lookup_europe` | 52,284 | 6 | - |

## audit_oia

| table | rows | columns | dates |
|---|---|---|---|
| `f27_auditor` | 3,434 | 11 | - |
| `f27_corporate_position` | 9,217 | 5 | `create_date` 2008-07-03 to 2026-09-25 |
| `f27_document_detail` | 110,857 | 18 | `accepted` 1995-09-28 to 2026-09-23 |
| `f27_document_detail_files` | 323,977 | 10 | `create_date` 2009-02-03 to 2026-09-24 |
| `f27_person` | 20,138 | 9 | `create_date` 2008-07-11 to 2026-09-10 |
| `f27_person_filing` | 198,973 | 7 | `create_date` 2009-01-29 to 2026-09-10 |
| `f27_person_positions` | 219,110 | 5 | `create_date` 2009-01-29 to 2026-09-10 |
| `f27_sec_locations` | 327 | 5 | - |
| `f28_auditor` | 14,110 | 11 | - |
| `f28_foundation_codes` | 14 | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f28_ntee_codes` | 605 | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f28_ntee_common_codes` | 26 | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f28_sub_cla_cod` | 54 | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f29_auditor` | 1,659 | 11 | - |
| `f29_corporate_position` | 9,217 | 5 | `create_date` 2008-07-03 to 2026-09-25 |
| `f29_document_detail` | 9,671 | 18 | `accepted` 1995-09-28 to 2026-09-23 |
| `f29_document_detail_files` | 27,161 | 10 | `create_date` 2009-02-03 to 2026-09-24 |
| `f29_person` | 9,972 | 9 | `create_date` 2008-07-17 to 2026-09-10 |
| `f29_person_filing` | 18,442 | 7 | `create_date` 2009-02-03 to 2026-09-10 |
| `f29_person_positions` | 21,225 | 5 | `create_date` 2009-02-03 to 2026-09-10 |
| `f29_sec_locations` | 327 | 5 | - |
| `f30_auditor` | 9,615 | 11 | - |
| `f30_foundation_codes` | 14 | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f30_ntee_codes` | 605 | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f30_ntee_common_codes` | 26 | 4 | `create_date` 2009-06-23 to 2009-06-23 |
| `f30_sub_cla_cod` | 54 | 5 | `create_date` 2009-06-23 to 2009-06-23 |
| `f35_deleted_keys` | 116,971 | 1 | - |
| `f35_ria_adv_sa_direct_owners` | 3,634,163 | 15 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sb_indirect_owners` | 1,079,633 | 16 | `create_date` 2010-10-20 to 2026-09-25 |
| `f35_ria_adv_sd_10_con_per` | 63,597 | 18 | `effective_date` 1914-07-14 to 2066-12-05 |
| `f35_ria_adv_sd_1b_other_names` | 1,262,755 | 6 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_1f_other_offices` | 1,666,580 | 13 | `create_date` 2010-10-20 to 2026-09-25 |
| `f35_ria_adv_sd_1i_www_addresses` | 3,036,317 | 5 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_1k_books_records` | 1,760,315 | 16 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_1l_for_reg` | 134,952 | 7 | `create_date` 2011-02-19 to 2026-09-25 |
| `f35_ria_adv_sd_2a1_sec_exe_ord` | 114 | 6 | `order_date` 1997-07-08 to 2021-06-11 |
| `f35_ria_adv_sd_2a7_aff_adv` | 2,640 | 7 | `create_date` 2010-03-11 to 2012-11-05 |
| `f35_ria_adv_sd_2a8_new_for_adv` | 209,696 | 6 | `create_date` 2010-03-11 to 2026-09-25 |
| `f35_ria_adv_sd_2a9_mul_adv` | 202,298 | 7 | `create_date` 2010-03-11 to 2026-09-24 |
| `f35_ria_adv_sd_4_successions` | 2,401 | 7 | `create_date` 2011-03-08 to 2026-09-10 |
| `f35_ria_adv_sd_7a_aff_adv_dea` | 3,082,501 | 9 | `create_date` 2010-10-19 to 2026-09-25 |
| `f35_ria_adv_sd_7b_lim_par` | 144,695 | 11 | `create_date` 2010-10-20 to 2015-02-02 |
| `f35_ria_adv_sd_9c_accountant` | 174,464 | 19 | `create_date` 2011-02-23 to 2026-09-25 |
| `f35_ria_adv_sd_miscellaneous` | 360,331 | 5 | `create_date` 2010-03-11 to 2026-09-25 |
| `f35_ria_form_url_to_live` | 1,219,026 | 5 | `date_submitted` 2007-04-26 to 2026-09-23 |
| `f35_ria_sd9_acc_to_aud` | 174,459 | 7 | `create_date` 2011-02-24 to 2026-09-26 |
| `f35_ria_sd_5g3_public_funds` | 246,090 | 13 | - |
| `f35_ria_sd_7b_admin` | 1,501,326 | 21 | - |
| `f35_ria_sd_7b_auditor` | 1,847,998 | 21 | - |
| `f35_ria_sd_7b_custodian` | 4,358,201 | 17 | - |
| `f35_ria_sd_7b_feeder_fund` | 527,992 | 10 | - |
| `f35_ria_sd_7b_marketer` | 928,260 | 16 | - |
| `f35_ria_sd_7b_prime_broker` | 652,120 | 16 | - |
| `f35_ria_sd_7b_private_funds` | 2,197,538 | 39 | - |
| `f36_deleted_keys` | 1,082,915 | 1 | - |
| `f36_ria_adv_sa_direct_owners` | 237,312 | 15 | `create_date` 2010-10-19 to 2026-09-25 |
| `f36_ria_adv_sb_indirect_owners` | 71,697 | 16 | `create_date` 2011-02-19 to 2026-09-25 |
| `f36_ria_adv_sd_10_con_per` | 4,714 | 18 | `effective_date` 1914-07-14 to 2026-12-12 |
| `f36_ria_adv_sd_1b_other_names` | 28,459 | 6 | `create_date` 2011-02-21 to 2026-09-25 |
| `f36_ria_adv_sd_1f_other_offices` | 53,978 | 13 | `create_date` 2010-10-21 to 2026-09-25 |
| `f36_ria_adv_sd_1i_www_addresses` | 156,191 | 5 | `create_date` 2010-10-19 to 2026-09-25 |
| `f36_ria_adv_sd_1k_books_records` | 70,773 | 16 | `create_date` 2010-10-20 to 2026-09-25 |
| `f36_ria_adv_sd_1l_for_reg` | 7,848 | 7 | `create_date` 2011-02-21 to 2026-09-25 |
| `f36_ria_adv_sd_2a1_sec_exe_ord` | 5 | 6 | `order_date` 1997-07-08 to 1998-01-16 |
| `f36_ria_adv_sd_2a7_aff_adv` | 468 | 7 | `create_date` 2010-03-11 to 2012-09-10 |
| `f36_ria_adv_sd_2a8_new_for_adv` | 23,564 | 6 | `create_date` 2010-03-11 to 2026-09-25 |
| `f36_ria_adv_sd_2a9_mul_adv` | 22,981 | 7 | `create_date` 2010-03-11 to 2026-09-24 |
| `f36_ria_adv_sd_4_successions` | 179 | 7 | `create_date` 2012-07-12 to 2026-09-10 |
| `f36_ria_adv_sd_7a_aff_adv_dea` | 177,431 | 9 | `create_date` 2010-10-19 to 2026-09-25 |
| `f36_ria_adv_sd_7b_lim_par` | 16,683 | 11 | `create_date` 2010-10-21 to 2015-02-02 |
| `f36_ria_adv_sd_9c_accountant` | 7,304 | 19 | `create_date` 2011-03-14 to 2026-09-25 |
| `f36_ria_adv_sd_miscellaneous` | 27,375 | 5 | `create_date` 2010-03-11 to 2026-09-25 |
| `f36_ria_form_url_to_live` | 29,087 | 5 | `date_submitted` 2007-04-26 to 2026-09-23 |
| `f36_ria_sd9_acc_to_aud` | 7,299 | 7 | `create_date` 2011-03-15 to 2026-09-26 |
| `f36_ria_sd_5g3_public_funds` | 6,775 | 13 | - |
| `f36_ria_sd_7b_admin` | 93,939 | 21 | - |
| `f36_ria_sd_7b_auditor` | 99,015 | 21 | - |
| `f36_ria_sd_7b_custodian` | 166,245 | 17 | - |
| `f36_ria_sd_7b_feeder_fund` | 24,523 | 10 | - |
| `f36_ria_sd_7b_marketer` | 33,215 | 16 | - |
| `f36_ria_sd_7b_prime_broker` | 28,080 | 16 | - |
| `f36_ria_sd_7b_private_funds` | 133,013 | 39 | - |
| `f43_admin` | 1,640 | 8 | - |
| `f43_broker` | 1,037 | 11 | - |
| `f43_fund_to_auditor` | 138,553 | 12 | - |
| `f53_auditor` | 664 | 11 | - |
| `f53_ins_assets` | 2,613,789 | 11 | - |
| `f53_ins_contacts_demographics` | 529,350 | 16 | - |
| `f53_ins_demographics` | 70,643 | 26 | - |
| `f53_ins_demographics_expanded` | 70,643 | 35 | - |
| `f53_ins_expenses` | 1,616,859 | 7 | - |
| `f53_ins_form_to_auditor_info` | 68,366 | 3 | - |
| `f53_ins_form_to_company` | 252 | 3 | - |
| `f53_ins_gen_int_bas` | 5,619,749 | 20 | `date_response`, not asked (too big) |
| `f53_ins_revenue` | 3,090,024 | 9 | - |
| `feed27_broker_dealer_focus_repor` | 110,867 | 72 | `period_ended_date` 2000-05-31 to 2026-07-03 |
| `feed28_non_profit_single_audit` | 1,105,650 | 100 | `fy_end_date` 1997-05-31 to 2026-06-30 |
| `feed29_current_broker_dealer_foc` | 9,674 | 60 | `period_ended_date` 2000-12-31 to 2026-07-03 |
| `feed30_current_non_profit_single` | 106,162 | 100 | `fy_end_date` 1997-06-30 to 2026-06-30 |
| `feed33_erisa` | 23,375,244 | 541 | `form_plan_year_begin_date`, not asked (too big) |
| `feed35_ria` | 1,052,325 | 174 | `sig_pag_dom_sig_date` 1911-07-11 to 2026-09-25 |
| `feed36_ria_current_engagements` | 86,381 | 174 | `sig_pag_dom_sig_date` 1924-05-05 to 2026-09-25 |
| `feed43_private_fund` | 224,183 | 35 | - |
| `feed53_naic` | 70,643 | 212 | `pcaob_reg_date` 2003-08-18 to 2023-10-22 |
| `feed59_bank_holding_company` | 240,758 | 356 | `date_insured`, not asked |
| `wrds_lookup_bank_holding` | 7,844 | 3 | - |
| `wrds_lookup_naic` | 8,637 | 5 | - |
| `wrds_lookup_non_profit_28` | 266,521 | 2 | - |
| `wrds_lookup_non_profit_30` | 98,395 | 2 | - |
| `wrds_lookup_private_fund` | 224,183 | 2 | - |

## auditsmp

| table | rows | columns | dates |
|---|---|---|---|
| `accfiler` | view | 209 | `pe_date` 2002-06-30 to 2020-03-31 |
| `auditcblock` | view | 252 | `curr_audlate_date` 2019-08-01 to 2020-02-03 |
| `auditchange` | view | 244 | `dismiss_date` 1999-11-01 to 2012-03-21 |
| `auditfees` | view | 216 | `fiscal_year_ended` 2000-09-30 to 2019-12-31 |
| `auditfeesr` | view | 216 | `fiscal_year_ended` 2000-09-30 to 2019-12-31 |
| `auditnonreli` | view | 234 | `res_begin_date` 1996-10-01 to 2014-01-01 |
| `auditopin` | view | 225 | `sig_date_of_op_s` 2000-02-02 to 2020-02-03 |
| `auditors` | view | 7 | `co_auditor_date_num_s` 2019-08-01 to 2020-02-03 |
| `auditorsinfo` | view | 15 | - |
| `auditsox302` | view | 218 | `period_end_date_num` 2002-09-28 to 2020-03-31 |
| `auditsox404` | view | 243 | `fye_ic_op` 2004-12-31 to 2019-12-31 |
| `benefit` | view | 219 | `sig_date_of_opin` 2002-03-01 to 2020-03-20 |
| `diroffichange` | view | 240 | `eff_date_s` 2003-09-05 to 2020-03-26 |
| `nt` | view | 224 | `pe_date_num` 2006-07-01 to 2006-09-30 |
| `revauditopin` | view | 226 | `fiscal_year_end_op` 1999-12-31 to 2019-12-31 |

## auditsmp_all

| table | rows | columns | dates |
|---|---|---|---|
| `accfiler` | 342 | 209 | `pe_date` 2002-06-30 to 2020-03-31 |
| `auditcblock` | 6 | 252 | `curr_audlate_date` 2019-08-01 to 2020-02-03 |
| `auditchange` | 3 | 244 | `dismiss_date` 1999-11-01 to 2012-03-21 |
| `auditfees` | 93 | 216 | `fiscal_year_ended` 2000-09-30 to 2019-12-31 |
| `auditfeesr` | 93 | 216 | `fiscal_year_ended` 2000-09-30 to 2019-12-31 |
| `auditnonreli` | 5 | 234 | `res_begin_date` 1996-10-01 to 2014-01-01 |
| `auditopin` | 94 | 225 | `sig_date_of_op_s` 2000-02-02 to 2020-02-03 |
| `auditors` | 6 | 7 | `co_auditor_date_num_s` 2019-08-01 to 2020-02-03 |
| `auditorsinfo` | 10 | 15 | - |
| `auditsox302` | 337 | 218 | `period_end_date_num` 2002-09-28 to 2020-03-31 |
| `auditsox404` | 148 | 243 | `fye_ic_op` 2004-12-31 to 2019-12-31 |
| `benefit` | 65 | 219 | `sig_date_of_opin` 2002-03-01 to 2020-03-20 |
| `diroffichange` | 183 | 240 | `eff_date_s` 2003-09-05 to 2020-03-26 |
| `nt` | 2 | 224 | `pe_date_num` 2006-07-01 to 2006-09-30 |
| `revauditopin` | 104 | 226 | `fiscal_year_end_op` 1999-12-31 to 2019-12-31 |

## bank

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_bank_crsp_link` | view | 6 | `dt_start` 1986-06-30 to 2024-07-12 |
| `wrds_bank_reg_vars` | view | 16 | `start_date` 1956-05-09 to 2024-12-31 |
| `wrds_call_rcfa_1` | view | 88 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfd_1` | view | 1504 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfd_2` | view | 711 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfn_1` | view | 49 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfw_1` | view | 32 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcoa_1` | view | 90 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcon_1` | view | 1505 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcon_2` | view | 1171 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcow_1` | view | 23 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_riad_1` | view | 373 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_te_1` | view | 128 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_holding_bhck_1` | view | 1501 | `rssd9999` 2000-03-31 to 2026-06-30 |
| `wrds_holding_bhck_2` | view | 830 | `rssd9999` 2000-03-31 to 2026-06-30 |
| `wrds_holding_other_1` | view | 1091 | `rssd9999` 2000-03-31 to 2026-06-30 |
| `wrds_struct_attributes_active` | view | 69 | `date_start` 1900-01-01 to 2026-11-03 |
| `wrds_struct_attributes_branches` | view | 69 | `date_start` 1934-01-01 to 2026-11-02 |
| `wrds_struct_attributes_closed` | view | 69 | `date_start` 1808-07-01 to 2026-08-31 |
| `wrds_struct_relationships` | view | 19 | `date_start` 1923-10-17 to 2026-11-01 |
| `wrds_struct_transformations` | view | 5 | `date_trans` 1936-02-02 to 2026-11-02 |

## bank_all

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_bank_crsp_link` | 1,495 | 6 | `dt_start` 1986-06-30 to 2024-07-12 |
| `wrds_bank_reg_vars` | 12,672 | 16 | `start_date` 1956-05-09 to 2024-12-31 |
| `wrds_call_rcfa_1` | 682,896 | 88 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfd_1` | 682,896 | 1504 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfd_2` | 682,896 | 711 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfn_1` | 682,896 | 49 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcfw_1` | 682,896 | 32 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcoa_1` | 682,896 | 90 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcon_1` | 682,792 | 1505 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcon_2` | 683,058 | 1171 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_rcow_1` | 682,896 | 23 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_riad_1` | 682,896 | 373 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_call_te_1` | 682,896 | 128 | `wrdsreportdate` 2001-03-31 to 2026-06-30 |
| `wrds_holding_bhck_1` | 330,410 | 1501 | `rssd9999` 2000-03-31 to 2026-06-30 |
| `wrds_holding_bhck_2` | 330,410 | 830 | `rssd9999` 2000-03-31 to 2026-06-30 |
| `wrds_holding_other_1` | 364,732 | 1091 | `rssd9999` 2000-03-31 to 2026-06-30 |
| `wrds_struct_attributes_active` | 62,162 | 69 | `date_start` 1900-01-01 to 2026-11-03 |
| `wrds_struct_attributes_branches` | 174,031 | 69 | `date_start` 1934-01-01 to 2026-11-02 |
| `wrds_struct_attributes_closed` | 162,690 | 69 | `date_start` 1808-07-01 to 2026-08-31 |
| `wrds_struct_relationships` | 289,512 | 19 | `date_start` 1923-10-17 to 2026-11-01 |
| `wrds_struct_transformations` | 59,249 | 5 | `date_trans` 1936-02-02 to 2026-11-02 |

## bank_premium_samp

| table | rows | columns | dates |
|---|---|---|---|
| `bic_to_lei` | 125 | 4 | `rec_bdate` 2018-01-31 to 2024-09-30 |
| `idrssd_to_lei` | 129 | 8 | - |
| `isin_to_lei` | 50,805 | 4 | `rec_bdate` 2019-04-04 to 2024-12-31 |
| `lei_main` | 25,810 | 45 | `rec_bdate` 2017-05-01 to 2024-12-31 |
| `rel_main` | 31,115 | 24 | `rec_bdate` 2017-05-17 to 2024-12-31 |
| `wrds_call_derived` | 748 | 631 | `date` 2001-03-31 to 2024-03-31 |
| `wrds_call_frgn_rcfd` | 120 | 635 | `d_dt` 2021-03-31 to 2024-03-31 |
| `wrds_call_research` | 1,302 | 372 | `date` 1976-03-31 to 2024-03-31 |
| `wrds_struct_rel_ultimate` | 52,852 | 11 | - |

## banksamp

| table | rows | columns | dates |
|---|---|---|---|
| `bic_to_lei` | view | 4 | `rec_bdate` 2018-01-31 to 2024-09-30 |
| `idrssd_to_lei` | view | 8 | - |
| `isin_to_lei` | view | 4 | `rec_bdate` 2019-04-04 to 2024-12-31 |
| `lei_main` | view | 45 | `rec_bdate` 2017-05-01 to 2024-12-31 |
| `rel_main` | view | 24 | `rec_bdate` 2017-05-17 to 2024-12-31 |
| `wrds_call_derived` | view | 631 | `date` 2001-03-31 to 2024-03-31 |
| `wrds_call_frgn_rcfd` | view | 635 | `d_dt` 2021-03-31 to 2024-03-31 |
| `wrds_call_research` | view | 372 | `date` 1976-03-31 to 2024-03-31 |
| `wrds_struct_rel_ultimate` | view | 11 | - |

## block

| table | rows | columns | dates |
|---|---|---|---|
| `block` | view | 37 | `mtgdate` 1996-01-03 to 2001-12-20 |
| `block2` | view | 37 | `mtgdate` 1996-01-03 to 2001-12-20 |
| `blockw` | view | 38 | `mtgdate` 1996-01-03 to 2001-12-20 |

## block_all

| table | rows | columns | dates |
|---|---|---|---|
| `block` | 20,975 | 37 | `mtgdate` 1996-01-03 to 2001-12-20 |
| `block2` | 20,975 | 37 | `mtgdate` 1996-01-03 to 2001-12-20 |
| `blockw` | 20,975 | 38 | `mtgdate` 1996-01-03 to 2001-12-20 |

## boardex

| table | rows | columns | dates |
|---|---|---|---|
| `eur_board_characteristics` | view | 28 | `annualreportdate` 1996-12-01 to 9000-01-01 |
| `eur_board_dir_announcements` | view | 12 | `announcementdate` 2002-02-02 to 2026-11-13 |
| `eur_board_dir_committees` | view | 16 | `datestartrole` 1991-01-01 to 2026-11-05 |
| `eur_board_education_assoc` | view | 9 | - |
| `eur_board_listed_assoc` | view | 11 | - |
| `eur_board_nfp_assoc` | view | 11 | - |
| `eur_board_other_assoc` | view | 11 | - |
| `eur_board_unlisted_assoc` | view | 11 | - |
| `eur_company_profile_advisors` | view | 5 | - |
| `eur_company_profile_details` | view | 30 | - |
| `eur_company_profile_market_cap` | view | 7 | - |
| `eur_company_profile_sr_mgrs` | view | 11 | `datestartrole` 1900-01-01 to 2026-11-12 |
| `eur_company_profile_stocks` | view | 7 | - |
| `eur_dir_characteristics` | view | 23 | `annualreportdate` 1996-12-01 to 9000-01-01 |
| `eur_dir_education_assoc` | view | 9 | - |
| `eur_dir_listed_assoc` | view | 11 | - |
| `eur_dir_nfp_assoc` | view | 11 | - |
| `eur_dir_other_assoc` | view | 11 | - |
| `eur_dir_profile_achievements` | view | 9 | `achievementdate` 1905-06-24 to 9999-12-31 |
| `eur_dir_profile_details` | view | 24 | `dob` 1900-01-01 to 2006-06-15 |
| `eur_dir_profile_education` | view | 10 | `awarddate` 1908-12-28 to 9999-12-31 |
| `eur_dir_profile_emp` | view | 15 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `eur_dir_profile_other_activ` | view | 11 | `startdate` 1900-01-01 to 2026-11-11 |
| `eur_dir_standard_remun` | view | 33 | `annualreportdate` 1996-12-01 to 2026-11-01 |
| `eur_dir_unlisted_assoc` | view | 11 | - |
| `eur_lookupcompany` | view | 4 | - |
| `eur_lookuproles` | view | 3 | - |
| `eur_lookupsalutations` | view | 1 | - |
| `eur_ltip_compensation` | view | 25 | `annualreportdate` 1997-12-01 to 2026-03-01 |
| `eur_ltip_wealth` | view | 25 | `annualreportdate` 1997-12-01 to 2026-11-01 |
| `eur_options_compensation` | view | 19 | `annualreportdate` 1997-12-01 to 2026-03-01 |
| `eur_options_wealth` | view | 19 | `annualreportdate` 1997-12-01 to 2026-11-01 |
| `eur_wrds_company_dir_names` | view | 11 | `annualreportdate` 1996-12-01 to 9000-01-01 |
| `eur_wrds_company_names` | view | 8 | - |
| `eur_wrds_company_networks` | view | 22 | `startcompanydatestartrole` 1900-01-01 to 2026-11-09 |
| `eur_wrds_company_profile` | view | 38 | - |
| `eur_wrds_company_region` | view | 5 | - |
| `eur_wrds_dir_profile_all` | view | 47 | `dob` 1900-01-01 to 2006-06-15 |
| `eur_wrds_dir_profile_emp` | view | 19 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `eur_wrds_individual_networks` | view | 20 | - |
| `eur_wrds_org_composition` | view | 10 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `eur_wrds_org_summary` | view | 66 | `annualreportdate` 1997-03-01 to 2026-08-01 |
| `na_board_characteristics` | view | 28 | `annualreportdate` 1997-07-01 to 9000-01-01 |
| `na_board_dir_announcements` | view | 12 | `announcementdate` 2001-01-05 to 2026-11-13 |
| `na_board_dir_committees` | view | 16 | `datestartrole` 1988-01-01 to 2026-11-13 |
| `na_board_education_assoc` | view | 9 | - |
| `na_board_listed_assoc` | view | 11 | - |
| `na_board_nfp_assoc` | view | 11 | - |
| `na_board_other_assoc` | view | 11 | - |
| `na_board_unlisted_assoc` | view | 11 | - |
| `na_company_profile_advisors` | view | 5 | - |
| `na_company_profile_details` | view | 30 | - |
| `na_company_profile_market_cap` | view | 7 | - |
| `na_company_profile_sr_mgrs` | view | 11 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `na_company_profile_stocks` | view | 7 | - |
| `na_dir_characteristics` | view | 23 | `annualreportdate` 1997-07-01 to 9000-01-01 |
| `na_dir_education_assoc` | view | 9 | - |
| `na_dir_listed_assoc` | view | 11 | - |
| `na_dir_nfp_assoc` | view | 11 | - |
| `na_dir_other_assoc` | view | 11 | - |
| `na_dir_profile_achievements` | view | 9 | `achievementdate` 1900-05-21 to 9999-12-31 |
| `na_dir_profile_details` | view | 24 | `dob` 1900-01-01 to 2010-06-15 |
| `na_dir_profile_education` | view | 10 | `awarddate` 1907-12-28 to 9999-12-31 |
| `na_dir_profile_emp` | view | 15 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `na_dir_profile_other_activ` | view | 11 | `startdate` 1900-01-01 to 2026-11-12 |
| `na_dir_standard_remun` | view | 33 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `na_dir_unlisted_assoc` | view | 11 | - |
| `na_lookupcompany` | view | 4 | - |
| `na_lookuproles` | view | 3 | - |
| `na_lookupsalutations` | view | 1 | - |
| `na_ltip_compensation` | view | 25 | `annualreportdate` 1997-12-01 to 2026-04-01 |
| `na_ltip_wealth` | view | 25 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `na_options_compensation` | view | 19 | `annualreportdate` 1997-07-01 to 2026-04-01 |
| `na_options_wealth` | view | 19 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `na_wrds_company_dir_names` | view | 11 | `annualreportdate` 1997-07-01 to 9000-01-01 |
| `na_wrds_company_names` | view | 8 | - |
| `na_wrds_company_networks` | view | 22 | `startcompanydatestartrole` 1900-01-01 to 2026-11-12 |
| `na_wrds_company_profile` | view | 38 | - |
| `na_wrds_company_region` | view | 5 | - |
| `na_wrds_dir_profile_all` | view | 47 | `dob` 1900-01-01 to 2010-06-15 |
| `na_wrds_dir_profile_emp` | view | 19 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `na_wrds_individual_networks` | view | 20 | - |
| `na_wrds_org_composition` | view | 10 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `na_wrds_org_summary` | view | 66 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `uk_board_characteristics` | view | 28 | `annualreportdate` 1997-02-01 to 9000-01-01 |
| `uk_board_dir_announcements` | view | 12 | `announcementdate` 2001-09-18 to 2026-11-13 |
| `uk_board_dir_committees` | view | 16 | `datestartrole` 1989-11-01 to 2026-11-13 |
| `uk_board_education_assoc` | view | 9 | - |
| `uk_board_listed_assoc` | view | 11 | - |
| `uk_board_nfp_assoc` | view | 11 | - |
| `uk_board_other_assoc` | view | 11 | - |
| `uk_board_unlisted_assoc` | view | 11 | - |
| `uk_company_profile_advisors` | view | 5 | - |
| `uk_company_profile_details` | view | 30 | - |
| `uk_company_profile_market_cap` | view | 7 | - |
| `uk_company_profile_sr_mgrs` | view | 11 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_company_profile_stocks` | view | 7 | - |
| `uk_dir_characteristics` | view | 23 | `annualreportdate` 1997-02-01 to 9000-01-01 |
| `uk_dir_education_assoc` | view | 9 | - |
| `uk_dir_listed_assoc` | view | 11 | - |
| `uk_dir_nfp_assoc` | view | 11 | - |
| `uk_dir_other_assoc` | view | 11 | - |
| `uk_dir_profile_achievements` | view | 9 | `achievementdate` 1933-12-28 to 9999-12-31 |
| `uk_dir_profile_details` | view | 24 | `dob` 1900-01-01 to 2006-08-01 |
| `uk_dir_profile_education` | view | 10 | `awarddate` 1931-12-28 to 9999-12-31 |
| `uk_dir_profile_emp` | view | 15 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_dir_profile_other_activ` | view | 11 | `startdate` 1900-01-01 to 2026-11-11 |
| `uk_dir_standard_remun` | view | 33 | `annualreportdate` 1997-02-01 to 2026-10-01 |
| `uk_dir_unlisted_assoc` | view | 11 | - |
| `uk_lookupcompany` | view | 4 | - |
| `uk_lookuproles` | view | 3 | - |
| `uk_lookupsalutations` | view | 1 | - |
| `uk_ltip_compensation` | view | 25 | `annualreportdate` 1997-02-01 to 2026-03-01 |
| `uk_ltip_wealth` | view | 25 | `annualreportdate` 1997-02-01 to 2026-11-01 |
| `uk_options_compensation` | view | 19 | `annualreportdate` 1997-02-01 to 2026-05-01 |
| `uk_options_wealth` | view | 19 | `annualreportdate` 1997-02-01 to 2026-11-01 |
| `uk_wrds_company_dir_names` | view | 11 | `annualreportdate` 1997-02-01 to 9000-01-01 |
| `uk_wrds_company_names` | view | 8 | - |
| `uk_wrds_company_networks` | view | 22 | `startcompanydatestartrole` 1900-01-01 to 2026-11-13 |
| `uk_wrds_company_profile` | view | 38 | - |
| `uk_wrds_company_region` | view | 5 | - |
| `uk_wrds_dir_profile_all` | view | 47 | `dob` 1900-01-01 to 2006-08-01 |
| `uk_wrds_dir_profile_emp` | view | 19 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_wrds_individual_networks` | view | 20 | - |
| `uk_wrds_org_composition` | view | 10 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_wrds_org_summary` | view | 66 | `annualreportdate` 1997-02-01 to 2026-08-01 |

## boardex_eur

| table | rows | columns | dates |
|---|---|---|---|
| `eur_board_characteristics` | 188,599 | 28 | `annualreportdate` 1996-12-01 to 9000-01-01 |
| `eur_board_dir_announcements` | 112,300 | 12 | `announcementdate` 2002-02-02 to 2026-11-13 |
| `eur_board_dir_committees` | 707,215 | 16 | `datestartrole` 1991-01-01 to 2026-11-05 |
| `eur_board_education_assoc` | 23,638 | 9 | - |
| `eur_board_listed_assoc` | 311,714 | 11 | - |
| `eur_board_nfp_assoc` | 38,765 | 11 | - |
| `eur_board_other_assoc` | 193,713 | 11 | - |
| `eur_board_unlisted_assoc` | 842,128 | 11 | - |
| `eur_company_profile_advisors` | 13,374 | 5 | - |
| `eur_company_profile_details` | 457,505 | 30 | - |
| `eur_company_profile_market_cap` | 6,364 | 7 | - |
| `eur_company_profile_sr_mgrs` | 234,676 | 11 | `datestartrole` 1900-01-01 to 2026-11-12 |
| `eur_company_profile_stocks` | 6,912 | 7 | - |
| `eur_dir_characteristics` | 619,590 | 23 | `annualreportdate` 1996-12-01 to 9000-01-01 |
| `eur_dir_education_assoc` | 76,521,816 | 9 | - |
| `eur_dir_listed_assoc` | 123,628,344 | 11 | - |
| `eur_dir_nfp_assoc` | 8,254,611 | 11 | - |
| `eur_dir_other_assoc` | 45,314,744 | 11 | - |
| `eur_dir_profile_achievements` | 263,939 | 9 | `achievementdate` 1905-06-24 to 9999-12-31 |
| `eur_dir_profile_details` | 486,199 | 24 | `dob` 1900-01-01 to 2006-06-15 |
| `eur_dir_profile_education` | 699,751 | 10 | `awarddate` 1908-12-28 to 9999-12-31 |
| `eur_dir_profile_emp` | 4,170,529 | 15 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `eur_dir_profile_other_activ` | 496,077 | 11 | `startdate` 1900-01-01 to 2026-11-11 |
| `eur_dir_standard_remun` | 1,137,912 | 33 | `annualreportdate` 1996-12-01 to 2026-11-01 |
| `eur_dir_unlisted_assoc` | 88,258,088 | 11 | - |
| `eur_lookupcompany` | 12,243 | 4 | - |
| `eur_lookuproles` | 96,751 | 3 | - |
| `eur_lookupsalutations` | view | 1 | - |
| `eur_ltip_compensation` | 30,641 | 25 | `annualreportdate` 1997-12-01 to 2026-03-01 |
| `eur_ltip_wealth` | 53,508 | 25 | `annualreportdate` 1997-12-01 to 2026-11-01 |
| `eur_options_compensation` | 15,327 | 19 | `annualreportdate` 1997-12-01 to 2026-03-01 |
| `eur_options_wealth` | 42,670 | 19 | `annualreportdate` 1997-12-01 to 2026-11-01 |
| `eur_wrds_company_dir_names` | 1,153,670 | 11 | `annualreportdate` 1996-12-01 to 9000-01-01 |
| `eur_wrds_company_names` | 464,384 | 8 | - |
| `eur_wrds_company_networks` | 1,550,188 | 22 | `startcompanydatestartrole` 1900-01-01 to 2026-11-09 |
| `eur_wrds_company_profile` | 458,330 | 38 | - |
| `eur_wrds_company_region` | 457,675 | 5 | - |
| `eur_wrds_dir_profile_all` | 5,630,911 | 47 | `dob`, not asked (too big) |
| `eur_wrds_dir_profile_emp` | 4,212,615 | 19 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `eur_wrds_individual_networks` | 341,877,408 | 20 | - |
| `eur_wrds_org_composition` | 911,366 | 10 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `eur_wrds_org_summary` | 590,051 | 66 | `annualreportdate` 1997-03-01 to 2026-08-01 |

## boardex_na

| table | rows | columns | dates |
|---|---|---|---|
| `na_board_characteristics` | 517,979 | 28 | `annualreportdate` 1997-07-01 to 9000-01-01 |
| `na_board_dir_announcements` | 322,176 | 12 | `announcementdate` 2001-01-05 to 2026-11-13 |
| `na_board_dir_committees` | 2,408,586 | 16 | `datestartrole` 1988-01-01 to 2026-11-13 |
| `na_board_education_assoc` | 105,934 | 9 | - |
| `na_board_listed_assoc` | 925,825 | 11 | - |
| `na_board_nfp_assoc` | 338,981 | 11 | - |
| `na_board_other_assoc` | 1,329,034 | 11 | - |
| `na_board_unlisted_assoc` | 1,910,720 | 11 | - |
| `na_company_profile_advisors` | 40,657 | 5 | - |
| `na_company_profile_details` | 1,251,490 | 30 | - |
| `na_company_profile_market_cap` | 12,239 | 7 | - |
| `na_company_profile_sr_mgrs` | 987,471 | 11 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `na_company_profile_stocks` | 15,570 | 7 | - |
| `na_dir_characteristics` | 1,408,324 | 23 | `annualreportdate` 1997-07-01 to 9000-01-01 |
| `na_dir_education_assoc` | 392,136,800 | 9 | - |
| `na_dir_listed_assoc` | 405,182,784 | 11 | - |
| `na_dir_nfp_assoc` | 59,708,044 | 11 | - |
| `na_dir_other_assoc` | 398,239,936 | 11 | - |
| `na_dir_profile_achievements` | 1,353,969 | 9 | `achievementdate` 1900-05-21 to 9999-12-31 |
| `na_dir_profile_details` | 1,539,261 | 24 | `dob` 1900-01-01 to 2010-06-15 |
| `na_dir_profile_education` | 2,469,679 | 10 | `awarddate` 1907-12-28 to 9999-12-31 |
| `na_dir_profile_emp` | 10,847,955 | 15 | `datestartrole`, not asked (too big) |
| `na_dir_profile_other_activ` | 2,717,045 | 11 | `startdate` 1900-01-01 to 2026-11-12 |
| `na_dir_standard_remun` | 2,782,021 | 33 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `na_dir_unlisted_assoc` | 361,595,776 | 11 | - |
| `na_lookupcompany` | 27,135 | 4 | - |
| `na_lookuproles` | 96,751 | 3 | - |
| `na_lookupsalutations` | view | 1 | - |
| `na_ltip_compensation` | 571,731 | 25 | `annualreportdate` 1997-12-01 to 2026-04-01 |
| `na_ltip_wealth` | 535,192 | 25 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `na_options_compensation` | 533,772 | 19 | `annualreportdate` 1997-07-01 to 2026-04-01 |
| `na_options_wealth` | 682,648 | 19 | `annualreportdate` 1997-07-01 to 2026-11-01 |
| `na_wrds_company_dir_names` | 2,811,672 | 11 | `annualreportdate` 1997-07-01 to 9000-01-01 |
| `na_wrds_company_names` | 1,266,538 | 8 | - |
| `na_wrds_company_networks` | 5,042,375 | 22 | `startcompanydatestartrole`, not asked (too big) |
| `na_wrds_company_profile` | 1,253,826 | 38 | - |
| `na_wrds_company_region` | 1,251,594 | 5 | - |
| `na_wrds_dir_profile_all` | 17,388,648 | 47 | `dob`, not asked (too big) |
| `na_wrds_dir_profile_emp` | 10,920,306 | 19 | `datestartrole`, not asked (too big) |
| `na_wrds_individual_networks` | 1,616,481,408 | 20 | - |
| `na_wrds_org_composition` | 2,386,354 | 10 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `na_wrds_org_summary` | 1,368,850 | 66 | `annualreportdate` 1997-07-01 to 2026-11-01 |

## boardex_trial

| table | rows | columns | dates |
|---|---|---|---|
| `jr_board_characteristics` | 2,740 | 28 | `annualreportdate` 2000-06-01 to 9000-01-01 |
| `jr_board_dir_announcements` | 1,570 | 12 | `announcementdate` 2004-02-19 to 2024-12-23 |
| `jr_board_dir_committees` | 14,446 | 16 | `datestartrole` 1998-01-02 to 2024-12-04 |
| `jr_board_education_assoc` | 84 | 9 | - |
| `jr_board_listed_assoc` | 3,424 | 11 | - |
| `jr_board_nfp_assoc` | 447 | 11 | - |
| `jr_board_other_assoc` | 1,847 | 11 | - |
| `jr_board_unlisted_assoc` | 7,872 | 11 | - |
| `jr_company_profile_advisors` | 312 | 5 | - |
| `jr_company_profile_details` | 113 | 30 | - |
| `jr_company_profile_market_cap` | 31 | 7 | - |
| `jr_company_profile_sr_mgrs` | 2,004 | 11 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_company_profile_stocks` | 130 | 7 | - |
| `jr_dir_characteristics` | 6,267 | 23 | `annualreportdate` 2000-06-01 to 9000-01-01 |
| `jr_dir_education_assoc` | 255,994 | 9 | - |
| `jr_dir_listed_assoc` | 210,371 | 11 | - |
| `jr_dir_nfp_assoc` | view (empty) | 11 | - |
| `jr_dir_other_assoc` | view (empty) | 11 | - |
| `jr_dir_profile_achievements` | 6 | 9 | `achievementdate` 2006-11-22 to 2013-12-28 |
| `jr_dir_profile_details` | 1,289 | 24 | `dob` 1900-01-01 to 1988-06-15 |
| `jr_dir_profile_education` | 1 | 10 | `awarddate` 2017-12-28 to 2017-12-28 |
| `jr_dir_profile_emp` | 4,949 | 15 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_dir_profile_other_activ` | view (empty) | 11 | `startdate`, not asked |
| `jr_dir_standard_remun` | 13,597 | 33 | `annualreportdate` 2000-06-01 to 2024-11-01 |
| `jr_dir_unlisted_assoc` | view (empty) | 11 | - |
| `jr_ltip_compensation` | 1,066 | 25 | `annualreportdate` 2000-06-01 to 2024-03-01 |
| `jr_ltip_wealth` | 2,408 | 25 | `annualreportdate` 2000-06-01 to 2025-01-01 |
| `jr_options_compensation` | 256 | 19 | `annualreportdate` 2000-06-01 to 2023-12-01 |
| `jr_options_wealth` | 925 | 19 | `annualreportdate` 2000-06-01 to 2025-01-01 |
| `jr_wrds_company_dir_names` | 7,018 | 11 | `annualreportdate` 2000-06-01 to 9000-01-01 |
| `jr_wrds_company_names` | 131 | 8 | - |
| `jr_wrds_company_networks` | 14,636 | 22 | `startcompanydatestartrole` 1900-01-01 to 2024-12-02 |
| `jr_wrds_company_profile` | 130 | 38 | - |
| `jr_wrds_company_region` | 119 | 5 | - |
| `jr_wrds_dir_profile_all` | 4,956 | 47 | `dob` 1900-01-01 to 1991-04-01 |
| `jr_wrds_dir_profile_emp` | 4,982 | 19 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_wrds_individual_networks` | 210,371 | 20 | - |
| `jr_wrds_org_composition` | 3,938 | 10 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_wrds_org_summary` | 6,169 | 66 | `annualreportdate` 2000-06-01 to 2024-06-01 |
| `jr_wrds_org_summary_all` | 6,214 | 66 | `annualreportdate` 2000-06-01 to 2024-06-01 |

## boardex_uk

| table | rows | columns | dates |
|---|---|---|---|
| `uk_board_characteristics` | 171,686 | 28 | `annualreportdate` 1997-02-01 to 9000-01-01 |
| `uk_board_dir_announcements` | 96,703 | 12 | `announcementdate` 2001-09-18 to 2026-11-13 |
| `uk_board_dir_committees` | 683,686 | 16 | `datestartrole` 1989-11-01 to 2026-11-13 |
| `uk_board_education_assoc` | 15,959 | 9 | - |
| `uk_board_listed_assoc` | 203,304 | 11 | - |
| `uk_board_nfp_assoc` | 65,179 | 11 | - |
| `uk_board_other_assoc` | 193,000 | 11 | - |
| `uk_board_unlisted_assoc` | 671,961 | 11 | - |
| `uk_company_profile_advisors` | 21,156 | 5 | - |
| `uk_company_profile_details` | 367,085 | 30 | - |
| `uk_company_profile_market_cap` | 4,165 | 7 | - |
| `uk_company_profile_sr_mgrs` | 184,299 | 11 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_company_profile_stocks` | 4,347 | 7 | - |
| `uk_dir_characteristics` | 385,593 | 23 | `annualreportdate` 1997-02-01 to 9000-01-01 |
| `uk_dir_education_assoc` | 86,286,896 | 9 | - |
| `uk_dir_listed_assoc` | 104,834,384 | 11 | - |
| `uk_dir_nfp_assoc` | 11,815,084 | 11 | - |
| `uk_dir_other_assoc` | 91,494,920 | 11 | - |
| `uk_dir_profile_achievements` | 321,087 | 9 | `achievementdate` 1933-12-28 to 9999-12-31 |
| `uk_dir_profile_details` | 441,593 | 24 | `dob` 1900-01-01 to 2006-08-01 |
| `uk_dir_profile_education` | 640,203 | 10 | `awarddate` 1931-12-28 to 9999-12-31 |
| `uk_dir_profile_emp` | 3,988,869 | 15 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_dir_profile_other_activ` | 597,803 | 11 | `startdate` 1900-01-01 to 2026-11-11 |
| `uk_dir_standard_remun` | 834,947 | 33 | `annualreportdate` 1997-02-01 to 2026-10-01 |
| `uk_dir_unlisted_assoc` | 92,843,064 | 11 | - |
| `uk_lookupcompany` | 7,155 | 4 | - |
| `uk_lookuproles` | 96,751 | 3 | - |
| `uk_lookupsalutations` | view | 1 | - |
| `uk_ltip_compensation` | 72,954 | 25 | `annualreportdate` 1997-02-01 to 2026-03-01 |
| `uk_ltip_wealth` | 191,433 | 25 | `annualreportdate` 1997-02-01 to 2026-11-01 |
| `uk_options_compensation` | 27,588 | 19 | `annualreportdate` 1997-02-01 to 2026-05-01 |
| `uk_options_wealth` | 102,662 | 19 | `annualreportdate` 1997-02-01 to 2026-11-01 |
| `uk_wrds_company_dir_names` | 795,485 | 11 | `annualreportdate` 1997-02-01 to 9000-01-01 |
| `uk_wrds_company_names` | 372,529 | 8 | - |
| `uk_wrds_company_networks` | 1,254,993 | 22 | `startcompanydatestartrole` 1900-01-01 to 2026-11-13 |
| `uk_wrds_company_profile` | 367,685 | 38 | - |
| `uk_wrds_company_region` | 367,304 | 5 | - |
| `uk_wrds_dir_profile_all` | 5,548,110 | 47 | `dob`, not asked (too big) |
| `uk_wrds_dir_profile_emp` | 4,011,664 | 19 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_wrds_individual_networks` | 387,084,512 | 20 | - |
| `uk_wrds_org_composition` | 797,937 | 10 | `datestartrole` 1900-01-01 to 2026-11-13 |
| `uk_wrds_org_summary` | 369,847 | 66 | `annualreportdate` 1997-02-01 to 2026-08-01 |

## boardsmp

| table | rows | columns | dates |
|---|---|---|---|
| `jr_board_characteristics` | view | 28 | `annualreportdate` 2000-06-01 to 9000-01-01 |
| `jr_board_dir_announcements` | view | 12 | `announcementdate` 2004-02-19 to 2024-12-23 |
| `jr_board_dir_committees` | view | 16 | `datestartrole` 1998-01-02 to 2024-12-04 |
| `jr_board_education_assoc` | view | 9 | - |
| `jr_board_listed_assoc` | view | 11 | - |
| `jr_board_nfp_assoc` | view | 11 | - |
| `jr_board_other_assoc` | view | 11 | - |
| `jr_board_unlisted_assoc` | view | 11 | - |
| `jr_company_profile_advisors` | view | 5 | - |
| `jr_company_profile_details` | view | 30 | - |
| `jr_company_profile_market_cap` | view | 7 | - |
| `jr_company_profile_sr_mgrs` | view | 11 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_company_profile_stocks` | view | 7 | - |
| `jr_dir_characteristics` | view | 23 | `annualreportdate` 2000-06-01 to 9000-01-01 |
| `jr_dir_education_assoc` | view | 9 | - |
| `jr_dir_listed_assoc` | view | 11 | - |
| `jr_dir_nfp_assoc` | view (empty) | 11 | - |
| `jr_dir_other_assoc` | view (empty) | 11 | - |
| `jr_dir_profile_achievements` | view | 9 | `achievementdate` 2006-11-22 to 2013-12-28 |
| `jr_dir_profile_details` | view | 24 | `dob` 1900-01-01 to 1988-06-15 |
| `jr_dir_profile_education` | view | 10 | `awarddate` 2017-12-28 to 2017-12-28 |
| `jr_dir_profile_emp` | view | 15 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_dir_profile_other_activ` | view (empty) | 11 | `startdate`, not asked |
| `jr_dir_standard_remun` | view | 33 | `annualreportdate` 2000-06-01 to 2024-11-01 |
| `jr_dir_unlisted_assoc` | view (empty) | 11 | - |
| `jr_ltip_compensation` | view | 25 | `annualreportdate` 2000-06-01 to 2024-03-01 |
| `jr_ltip_wealth` | view | 25 | `annualreportdate` 2000-06-01 to 2025-01-01 |
| `jr_options_compensation` | view | 19 | `annualreportdate` 2000-06-01 to 2023-12-01 |
| `jr_options_wealth` | view | 19 | `annualreportdate` 2000-06-01 to 2025-01-01 |
| `jr_wrds_company_dir_names` | view | 11 | `annualreportdate` 2000-06-01 to 9000-01-01 |
| `jr_wrds_company_names` | view | 8 | - |
| `jr_wrds_company_networks` | view | 22 | `startcompanydatestartrole` 1900-01-01 to 2024-12-02 |
| `jr_wrds_company_profile` | view | 38 | - |
| `jr_wrds_company_region` | view | 5 | - |
| `jr_wrds_dir_profile_all` | view | 47 | `dob` 1900-01-01 to 1991-04-01 |
| `jr_wrds_dir_profile_emp` | view | 19 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_wrds_individual_networks` | view | 20 | - |
| `jr_wrds_org_composition` | view | 10 | `datestartrole` 1900-01-01 to 2025-01-02 |
| `jr_wrds_org_summary` | view | 66 | `annualreportdate` 2000-06-01 to 2024-06-01 |
| `jr_wrds_org_summary_all` | view | 66 | `annualreportdate` 2000-06-01 to 2024-06-01 |

## bvd_amadeus_trial

| table | rows | columns | dates |
|---|---|---|---|
| `amadeus_qvards` | 1 | 163 | - |
| `trial_amadeus_financials_v` | 920 | 89 | `closdate` 1997-12-31 to 2013-06-30 |
| `trial_amadeus_v` | 100 | 45 | `statusdate` 1962-07-10 to 2013-07-16 |

## bvd_bvdbankf_trial

| table | rows | columns | dates |
|---|---|---|---|
| `bvdbankf_bank` | 83 | 74 | `lei_first_assignment_date` 2012-06-06 to 2017-11-20 |
| `bvdbankf_financials` | 272 | 662 | `closdate` 2006-12-31 to 2017-12-31 |
| `bvdbankf_ish_guo_duo` | 83 | 66 | - |
| `bvdbankf_qvards` | 1 | 227 | - |
| `bvdbankf_stock_annual` | 95 | 37 | `closing_date` 2011-12-31 to 2017-12-31 |
| `bvdbankf_subsidiaries` | 835 | 23 | - |

## bvd_orbis_trial

| table | rows | columns | dates |
|---|---|---|---|
| `ob_all_cur_shh_1st_level_lms` | 961 | 21 | `_9033`, not asked |
| `ob_all_subs_first_level_lms` | 2,548 | 18 | `_9332`, not asked |
| `ob_banks_g_fins_usd_int_lms` | 84 | 115 | `closdate` 2010-09-30 to 2015-12-31 |
| `ob_banks_g_fins_usd_lms` | 171 | 115 | `closdate` 2010-12-31 to 2015-12-31 |
| `ob_ins_g_fins_usd_lms` | 138 | 49 | `closdate` 2010-06-30 to 2015-12-31 |
| `ob_w_company_id_table_lms` | 106 | 65 | `namechdt`, not asked |
| `ob_w_ind_g_fins_cfl_usd_int_lms` | 152 | 216 | `closdate` 2013-09-30 to 2015-12-31 |
| `ob_w_ind_g_fins_cfl_usd_lms` | 241 | 222 | `closdate` 2010-06-30 to 2015-12-31 |
| `orbis_qvards` | 1 | 304 | - |

## bvdsamp

| table | rows | columns | dates |
|---|---|---|---|
| `amadeus_qvards` | view | 163 | - |
| `bvdbankf_bank` | view | 74 | `lei_first_assignment_date` 2012-06-06 to 2017-11-20 |
| `bvdbankf_financials` | view | 662 | `closdate` 2006-12-31 to 2017-12-31 |
| `bvdbankf_ish_guo_duo` | view | 66 | - |
| `bvdbankf_qvards` | view | 227 | - |
| `bvdbankf_stock_annual` | view | 37 | `closing_date` 2011-12-31 to 2017-12-31 |
| `bvdbankf_subsidiaries` | view | 23 | - |
| `ob_all_cur_shh_1st_level_lms` | view | 21 | `_9033`, not asked |
| `ob_all_subs_first_level_lms` | view | 18 | `_9332`, not asked |
| `ob_banks_g_fins_usd_int_lms` | view | 115 | `closdate` 2010-09-30 to 2015-12-31 |
| `ob_banks_g_fins_usd_lms` | view | 115 | `closdate` 2010-12-31 to 2015-12-31 |
| `ob_ins_g_fins_usd_lms` | view | 49 | `closdate` 2010-06-30 to 2015-12-31 |
| `ob_w_company_id_table_lms` | view | 65 | `namechdt`, not asked |
| `ob_w_ind_g_fins_cfl_usd_int_lms` | view | 216 | `closdate` 2013-09-30 to 2015-12-31 |
| `ob_w_ind_g_fins_cfl_usd_lms` | view | 222 | `closdate` 2010-06-30 to 2015-12-31 |
| `orbis_qvards` | view | 304 | - |
| `trial_amadeus_financials_v` | view | 89 | `closdate` 1997-12-31 to 2013-06-30 |
| `trial_amadeus_v` | view | 45 | `statusdate` 1962-07-10 to 2013-07-16 |

## calcbench_trial

| table | rows | columns | dates |
|---|---|---|---|
| `breakout` | 54,033 | 13 | `end_date` 2008-12-31 to 2016-05-01 |
| `entity_names` | 11,030 | 7 | - |
| `normalized_fn` | 63,339 | 14 | `end_date` 2008-06-29 to 2016-05-01 |

## calcbnch

| table | rows | columns | dates |
|---|---|---|---|
| `breakout` | view | 13 | `end_date` 2008-12-31 to 2016-05-01 |
| `normalized_fn` | view | 14 | `end_date` 2008-06-29 to 2016-05-01 |

## candid_samp

| table | rows | columns | dates |
|---|---|---|---|
| `candid_3_year` | 30 | 78 | `period_begin` 2021-07-01 to 2023-09-01 |

## cboe

| table | rows | columns | dates |
|---|---|---|---|
| `cboe` | view | 17 | `date` 1986-01-02 to 2026-10-30 |

## cboe_all

| table | rows | columns | dates |
|---|---|---|---|
| `cboe` | 10,830 | 17 | `date` 1986-01-02 to 2026-10-30 |

## cboe_sample

| table | rows | columns | dates |
|---|---|---|---|
| `eqhvol` | 5,200 | 5 | `date_` 2023-12-01 to 2023-12-29 |
| `eqmaster` | 10 | 11 | `startdate` 2000-04-27 to 2023-07-31 |
| `eqprice` | 200 | 11 | `date_` 2023-12-01 to 2023-12-29 |
| `ivlisted` | 75,126 | 13 | `date_` 2023-12-01 to 2023-12-29 |
| `optcontract` | 7,308 | 21 | `expdate` 2023-12-01 to 2023-12-29 |
| `optprice` | 75,126 | 12 | `date_` 2023-12-01 to 2023-12-29 |
| `wrds_eq_opt_merged` | 7,308 | 4 | - |

## cboesamp

| table | rows | columns | dates |
|---|---|---|---|
| `eqhvol` | view | 5 | `date_` 2023-12-01 to 2023-12-29 |
| `eqmaster` | view | 11 | `startdate` 2000-04-27 to 2023-07-31 |
| `eqprice` | view | 11 | `date_` 2023-12-01 to 2023-12-29 |
| `ivlisted` | view | 13 | `date_` 2023-12-01 to 2023-12-29 |
| `optcontract` | view | 21 | `expdate` 2023-12-01 to 2023-12-29 |
| `optprice` | view | 12 | `date_` 2023-12-01 to 2023-12-29 |
| `wrds_eq_opt_merged` | view | 4 | - |

## cddsamp

| table | rows | columns | dates |
|---|---|---|---|
| `candid_3_year` | view | 78 | `period_begin` 2021-07-01 to 2023-09-01 |

## ciqsamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 326 | - |
| `ciqkeydev` | view | 13 | `speffectivedate` 2018-04-14 to 2023-12-08 |
| `ratings_ids` | view | 21 | - |
| `wrds_cik` | view | 6 | `startdate` 1997-02-15 to 2021-01-14 |
| `wrds_cik_trial` | view | 5 | `startdate` 1997-02-15 to 2008-07-17 |
| `wrds_ciqsymbol` | view | 19 | `startdate` 1968-01-02 to 2025-09-26 |
| `wrds_ciqsymbol_primary` | view | 19 | `startdate` 1968-01-02 to 2025-05-23 |
| `wrds_compensation` | view | 110 | `filingdate` 2011-01-07 to 2011-12-31 |
| `wrds_compensation_trial` | view | 110 | `filingdate` 1999-03-08 to 2019-06-19 |
| `wrds_compensationdetails` | view | 86 | `filingdate` 2011-01-07 to 2011-11-30 |
| `wrds_compensationdetails_trial` | view | 86 | `filingdate` 2002-02-22 to 2019-05-14 |
| `wrds_consideration_financials` | view | 27 | `lateststatusdatetime` 1999-06-01 to 2025-02-13 |
| `wrds_cusip` | view | 6 | `startdate` 1968-01-02 to 2025-09-25 |
| `wrds_cusip_trial` | view | 5 | `startdate` 1968-01-02 to 2019-06-12 |
| `wrds_debt` | view | 52 | `periodenddate` 2007-12-31 to 2011-11-05 |
| `wrds_debt_trial` | view | 52 | `periodenddate` 1991-12-31 to 2010-12-31 |
| `wrds_eassessment` | view | 35 | `assessmentdate` 2011-01-05 to 2011-12-29 |
| `wrds_entity_info` | view | 18 | - |
| `wrds_equity` | view | 38 | `periodenddate` 2007-12-31 to 2011-11-05 |
| `wrds_equity_trial` | view | 38 | `periodenddate` 1986-12-31 to 2011-01-29 |
| `wrds_erating` | view | 30 | `ratingdate` 2011-01-07 to 2011-12-29 |
| `wrds_gvkey` | view | 6 | `startdate` 1986-01-01 to 2018-05-23 |
| `wrds_gvkey_trial` | view | 5 | `startdate` 1986-01-01 to 2018-05-23 |
| `wrds_inst_info` | view | 18 | - |
| `wrds_irating` | view | 41 | `ratingdate` 2011-01-03 to 2011-12-23 |
| `wrds_isin` | view | 6 | `startdate` 1973-09-26 to 2025-09-26 |
| `wrds_isin_trial` | view | 5 | `startdate` 1974-03-19 to 2019-06-13 |
| `wrds_keydev_div_trial` | view | 26 | `announcedate` 1970-11-20 to 2011-03-22 |
| `wrds_keydev_trial` | view | 13 | `announcedate` 1972-12-14 to 2011-06-26 |
| `wrds_offerings` | view | 87 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_advisors` | view | 15 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_feat` | view | 11 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_proceeds` | view | 10 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_registration` | view | 58 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_rel` | view | 17 | `poannounced` 2011-01-04 to 2011-12-30 |
| `wrds_professional` | view | 39 | - |
| `wrds_professional_trial` | view | 39 | - |
| `wrds_sassessment` | view | 36 | `assessmentdate` 2011-01-03 to 2011-12-23 |
| `wrds_sec_info` | view | 21 | `maturitydate` 2011-07-27 to 2111-03-16 |
| `wrds_srating` | view | 38 | `ratingdate` 2011-01-01 to 2011-12-31 |
| `wrds_summary` | view | 121 | `periodenddate` 2007-12-31 to 2011-11-05 |
| `wrds_ticker` | view | 6 | `startdate` 1968-01-02 to 2025-09-25 |
| `wrds_ticker_trial` | view | 5 | `startdate` 1975-01-06 to 2019-06-13 |
| `wrds_trans_advisors` | view | 20 | `lateststatusdatetime` 1999-06-30 to 2025-02-13 |
| `wrds_trans_conditions` | view | 12 | `lateststatusdatetime` 1994-08-04 to 2025-02-13 |
| `wrds_trans_considerations` | view | 54 | `lateststatusdatetime` 1990-08-10 to 2025-02-13 |
| `wrds_trans_features` | view | 12 | `lateststatusdatetime` 1990-08-10 to 2025-05-23 |
| `wrds_transactions` | view | 161 | `lateststatusdatetime` 1990-08-10 to 2025-05-23 |
| `wrds_transcript_detail` | view | 19 | `mostimportantdateutc` 2005-07-21 to 2008-10-30 |
| `wrds_transcript_person` | view | 13 | - |

## ciqsamp_capstrct

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_debt` | 14,306 | 52 | `periodenddate` 2007-12-31 to 2011-11-05 |
| `wrds_debt_trial` | 26,453 | 52 | `periodenddate` 1991-12-31 to 2010-12-31 |
| `wrds_equity` | 2,211 | 38 | `periodenddate` 2007-12-31 to 2011-11-05 |
| `wrds_equity_trial` | 21,780 | 38 | `periodenddate` 1986-12-31 to 2011-01-29 |
| `wrds_summary` | 3,629 | 121 | `periodenddate` 2007-12-31 to 2011-11-05 |

## ciqsamp_common

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 326 | - |
| `wrds_cik` | 119 | 6 | `startdate` 1997-02-15 to 2021-01-14 |
| `wrds_cik_trial` | 111 | 5 | `startdate` 1997-02-15 to 2008-07-17 |
| `wrds_ciqsymbol` | 444,304 | 19 | `startdate` 1968-01-02 to 2025-09-26 |
| `wrds_ciqsymbol_primary` | 340 | 19 | `startdate` 1968-01-02 to 2025-05-23 |
| `wrds_cusip` | 46,167 | 6 | `startdate` 1968-01-02 to 2025-09-25 |
| `wrds_cusip_trial` | 22,757 | 5 | `startdate` 1968-01-02 to 2019-06-12 |
| `wrds_gvkey` | 93 | 6 | `startdate` 1986-01-01 to 2018-05-23 |
| `wrds_gvkey_trial` | 93 | 5 | `startdate` 1986-01-01 to 2018-05-23 |
| `wrds_isin` | 203,936 | 6 | `startdate` 1973-09-26 to 2025-09-26 |
| `wrds_isin_trial` | 176,847 | 5 | `startdate` 1974-03-19 to 2019-06-13 |
| `wrds_ticker` | 120,402 | 6 | `startdate` 1968-01-02 to 2025-09-25 |
| `wrds_ticker_trial` | 131,817 | 5 | `startdate` 1975-01-06 to 2019-06-13 |

## ciqsamp_keydev

| table | rows | columns | dates |
|---|---|---|---|
| `ciqkeydev` | 100,700 | 13 | `speffectivedate` 2018-04-14 to 2023-12-08 |
| `wrds_keydev_div_trial` | 24,665 | 26 | `announcedate` 1970-11-20 to 2011-03-22 |
| `wrds_keydev_trial` | 81,607 | 22 | `announcedate` 1973-06-30 to 2011-12-19 |

## ciqsamp_pplintel

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_cik_trial` | 111 | 5 | `startdate` 1997-02-15 to 2008-07-17 |
| `wrds_compensation` | 1,397 | 110 | `filingdate` 2011-01-07 to 2011-12-31 |
| `wrds_compensation_trial` | 16,851 | 110 | `filingdate` 1999-03-08 to 2019-06-19 |
| `wrds_compensationdetails` | 1,849 | 86 | `filingdate` 2011-01-07 to 2011-11-30 |
| `wrds_compensationdetails_trial` | 26,973 | 86 | `filingdate` 2002-02-22 to 2019-05-14 |
| `wrds_cusip_trial` | 22,757 | 5 | `startdate` 1968-01-02 to 2019-06-12 |
| `wrds_debt_trial` | 26,453 | 52 | `periodenddate` 1991-12-31 to 2010-12-31 |
| `wrds_equity_trial` | 21,780 | 38 | `periodenddate` 1986-12-31 to 2011-01-29 |
| `wrds_gvkey_trial` | 93 | 5 | `startdate` 1986-01-01 to 2018-05-23 |
| `wrds_isin_trial` | 176,847 | 5 | `startdate` 1974-03-19 to 2019-06-13 |
| `wrds_keydev_trial` | 86,660 | 13 | `announcedate` 1972-12-14 to 2011-06-26 |
| `wrds_professional` | 49,833 | 39 | - |
| `wrds_professional_trial` | 43,113 | 39 | - |
| `wrds_ticker_trial` | 131,817 | 5 | `startdate` 1975-01-06 to 2019-06-13 |

## ciqsamp_ratings

| table | rows | columns | dates |
|---|---|---|---|
| `ratings_ids` | 794,238 | 21 | - |
| `wrds_eassessment` | 205 | 35 | `assessmentdate` 2011-01-05 to 2011-12-29 |
| `wrds_entity_info` | 209 | 18 | - |
| `wrds_erating` | 240 | 30 | `ratingdate` 2011-01-07 to 2011-12-29 |
| `wrds_inst_info` | 88,239 | 18 | - |
| `wrds_irating` | 1,361 | 41 | `ratingdate` 2011-01-03 to 2011-12-23 |
| `wrds_sassessment` | 843 | 36 | `assessmentdate` 2011-01-03 to 2011-12-23 |
| `wrds_sec_info` | 3,846 | 21 | `maturitydate` 2011-07-27 to 2111-03-16 |
| `wrds_srating` | 86,738 | 38 | `ratingdate` 2011-01-01 to 2011-12-31 |

## ciqsamp_transactions

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_consideration_financials` | 350 | 27 | `lateststatusdatetime` 1999-06-01 to 2025-02-13 |
| `wrds_offerings` | 2,631 | 87 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_advisors` | 13,090 | 15 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_feat` | 7,906 | 11 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_proceeds` | 7,020 | 10 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_registration` | 3,472 | 58 | `announced` 2011-01-04 to 2011-12-30 |
| `wrds_offerings_rel` | 2,468 | 17 | `poannounced` 2011-01-04 to 2011-12-30 |
| `wrds_trans_advisors` | 404 | 20 | `lateststatusdatetime` 1999-06-30 to 2025-02-13 |
| `wrds_trans_conditions` | 190 | 12 | `lateststatusdatetime` 1994-08-04 to 2025-02-13 |
| `wrds_trans_considerations` | 190 | 54 | `lateststatusdatetime` 1990-08-10 to 2025-02-13 |
| `wrds_trans_features` | 1,350 | 12 | `lateststatusdatetime` 1990-08-10 to 2025-05-23 |
| `wrds_transactions` | 1,080 | 161 | `lateststatusdatetime` 1990-08-10 to 2025-05-23 |

## ciqsamp_transcripts

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_transcript_detail` | 20 | 19 | `mostimportantdateutc` 2005-07-21 to 2008-10-30 |
| `wrds_transcript_person` | 2,089 | 13 | - |

## cisdmsmp

| table | rows | columns | dates |
|---|---|---|---|
| `active_fund_info` | view | 142 | `na_date` 2011-12-31 to 2013-08-13 |
| `active_returns_assets` | view | 5 | `date` 1994-01-31 to 2013-06-30 |

## columnar

| table | rows | columns | dates |
|---|---|---|---|
| `storage` | view (empty) | 2 | - |

## comp

| table | rows | columns | dates |
|---|---|---|---|
| `aco_amda` | view | 10 | `datadate` 1973-12-31 to 2027-05-31 |
| `aco_imda` | view | 11 | `datadate` 1994-03-31 to 2026-09-30 |
| `aco_indfnta` | view | 446 | `datadate` 1951-12-31 to 2026-09-30 |
| `aco_indfntq` | view | 274 | `datadate` 1962-03-31 to 2026-09-30 |
| `aco_indfntytd` | view | 172 | `datadate` 1962-03-31 to 2026-09-30 |
| `aco_indsta` | view | 886 | `datadate` 1951-08-31 to 2026-09-30 |
| `aco_indstq` | view | 541 | `datadate` 1962-02-28 to 2026-10-31 |
| `aco_indstytd` | view | 337 | `datadate` 1962-02-28 to 2026-10-31 |
| `aco_notesa` | view | 12 | `datadate` 1999-01-31 to 2027-05-31 |
| `aco_notesq` | view | 13 | `datadate` 1999-01-31 to 2027-05-31 |
| `aco_notessa` | view | 13 | `datadate` 1999-01-31 to 2026-11-30 |
| `aco_notesytd` | view | 13 | `datadate` 1999-01-31 to 2027-05-31 |
| `aco_pnfnda` | view | 164 | `datadate` 1973-06-30 to 2026-09-30 |
| `aco_pnfndq` | view | 21 | `datadate` 1996-07-31 to 2026-10-31 |
| `aco_pnfndytd` | view | 21 | `datadate` 1996-07-31 to 2026-10-31 |
| `aco_pnfnta` | view | 85 | `datadate` 1985-12-31 to 2026-09-30 |
| `aco_pnfntq` | view | 14 | `datadate` 2006-06-30 to 2026-09-30 |
| `aco_pnfntytd` | view | 14 | `datadate` 2007-03-31 to 2026-03-31 |
| `aco_transa` | view | 15 | `datadate` 1946-12-31 to 2026-10-31 |
| `aco_transq` | view | 16 | `datadate` 1961-03-31 to 2026-10-31 |
| `aco_transsa` | view | 16 | `datadate` 1975-03-31 to 2026-10-31 |
| `aco_transytd` | view | 16 | `datadate` 1961-03-31 to 2026-10-31 |
| `adsprate` | view | 5 | `datadate` 1978-11-30 to 2017-02-28 |
| `asec_amda` | view (empty) | 12 | `datadate`, not asked |
| `asec_imda` | view | 12 | `datadate` 2011-03-31 to 2018-03-31 |
| `asec_notesa` | view | 14 | `datadate` 1999-06-30 to 2026-06-30 |
| `asec_notesq` | view | 14 | `datadate` 2004-12-31 to 2026-09-30 |
| `asec_transa` | view | 17 | `datadate` 2007-12-31 to 2026-09-30 |
| `asec_transq` | view | 17 | `datadate` 2008-03-31 to 2026-09-30 |
| `bank_aacctchg` | view | 8 | `datadate` 2007-12-31 to 2024-09-30 |
| `bank_adesind` | view | 29 | `apdedate` 2003-06-30 to 2026-09-30 |
| `bank_afnd1` | view | 235 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_afnd2` | view | 200 | `datadate` 1955-12-31 to 2026-09-30 |
| `bank_afnddc1` | view | 235 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_afnddc2` | view | 200 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_afntind` | view | 430 | `datadate` 1959-12-31 to 2026-09-30 |
| `bank_funda` | view | 465 | `apdedate` 2003-06-30 to 2026-09-30 |
| `bank_funda_fncd` | view | 409 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_fundq` | view | 559 | `apdedateq` 2002-09-30 to 2026-09-30 |
| `bank_fundq_fncd` | view | 629 | `datadate` 1961-12-31 to 2026-09-30 |
| `bank_iacctchg` | view | 9 | `datadate` 2007-03-31 to 2024-03-31 |
| `bank_idesind` | view | 35 | `apdedateq` 2002-09-30 to 2026-09-30 |
| `bank_ifndq` | view | 613 | `datadate` 1961-12-31 to 2026-09-30 |
| `bank_ifndytd` | view | 423 | `datadate` 1962-03-31 to 2026-09-30 |
| `bank_ifntq` | view | 310 | `datadate` 1961-12-31 to 2026-09-30 |
| `bank_ifntytd` | view | 215 | `datadate` 1962-03-31 to 2026-09-30 |
| `bank_names` | view | 11 | - |
| `bank_namesq` | view | 11 | - |
| `chars` | view (empty) | 39 | - |
| `co_aacctchg` | view | 8 | `datadate` 2007-06-30 to 2026-06-30 |
| `co_aaudit` | view | 12 | `datadate` 1964-12-31 to 2027-05-31 |
| `co_acthist` | view | 20 | `datadate` 1988-01-20 to 2026-11-18 |
| `co_adesind` | view | 33 | `apdedate` 2002-12-31 to 2026-10-25 |
| `co_adjfact` | view | 5 | `effdate` 1900-01-01 to 2026-11-18 |
| `co_afnd1` | view | 539 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afnd2` | view | 468 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afnddc1` | view | 539 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afnddc2` | view | 468 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afntind1` | view | 539 | `datadate` 1950-12-31 to 2026-10-31 |
| `co_afntind2` | view | 468 | `datadate` 1950-12-31 to 2027-05-31 |
| `co_ainvval` | view | 8 | `datadate` 1950-06-30 to 2026-09-30 |
| `co_amkt` | view | 14 | `datadate` 1950-06-30 to 2027-05-31 |
| `co_busdescl` | view | 2 | - |
| `co_cotype` | view | 4 | `effdate` 1900-01-01 to 2026-11-13 |
| `co_filedate` | view | 7 | `datadate` 1966-08-31 to 2026-10-31 |
| `co_fortune` | view | 5 | `datadate` 1982-12-31 to 2025-12-31 |
| `co_hgic` | view | 8 | `indfrom` 1999-06-30 to 2026-11-18 |
| `co_iacctchg` | view | 9 | `datadate` 2007-02-28 to 2026-07-31 |
| `co_iaudit` | view | 10 | `datadate` 2002-03-31 to 2027-05-31 |
| `co_idesind` | view | 36 | `apdedateq` 2002-03-31 to 2026-11-01 |
| `co_ifndq` | view | 937 | `datadate` 1961-03-31 to 2026-10-31 |
| `co_ifndsa` | view | 463 | `datadate` 1965-06-30 to 2026-10-31 |
| `co_ifndytd` | view | 741 | `datadate` 1961-03-31 to 2026-10-31 |
| `co_ifntq` | view | 473 | `datadate` 1961-07-31 to 2027-05-31 |
| `co_ifntsa` | view | 236 | `datadate` 1985-06-30 to 2026-10-31 |
| `co_ifntytd` | view | 384 | `datadate` 1961-07-31 to 2026-10-31 |
| `co_imkt` | view | 15 | `datadate` 1950-03-31 to 2026-11-30 |
| `co_industry` | view | 8 | `datadate` 1950-12-31 to 2026-09-30 |
| `co_ipcd` | view | 5 | `datadate` 1955-12-31 to 2026-09-30 |
| `co_mthly` | view | 4 | `datadate` 1978-11-30 to 2026-10-31 |
| `co_offtitl` | view | 4 | - |
| `company` | view | 40 | `dldte` 1964-01-10 to 2026-11-16 |
| `currency` | view | 6 | `isocurbd` 1900-01-01 to 2024-04-30 |
| `dd_group` | view | 5 | - |
| `dd_group_xref` | view | 3 | - |
| `dd_item` | view | 15 | - |
| `dd_package` | view | 4 | - |
| `ecind_desc` | view | 8 | - |
| `ecind_mth` | view | 55 | `datadate` 1981-01-31 to 2030-12-31 |
| `exrt_dly` | view | 5 | `datadate` 1982-02-01 to 2026-11-18 |
| `exrt_mth` | view | 22 | `datadate` 1982-01-31 to 2026-11-30 |
| `funda` | view | 949 | `datadate` 1950-06-30 to 2027-05-31 |
| `funda_fncd` | view | 888 | `datadate` 1950-06-30 to 2027-05-31 |
| `fundq` | view | 648 | `datadate` 1961-03-31 to 2027-05-31 |
| `fundq_fncd` | view | 778 | `datadate` 1961-03-31 to 2027-05-31 |
| `g_chars` | view (empty) | 44 | - |
| `g_co_aaudit` | view | 12 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_adesind` | view | 33 | `apdedate`, not asked |
| `g_co_afnd1` | view | 512 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afnd2` | view | 465 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afnddc1` | view | 512 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afnddc2` | view | 465 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afntind1` | view | 512 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afntind2` | view | 465 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_ainvval` | view | 8 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_gsuppl` | view | 153 | `auopdate` 1991-02-25 to 2008-08-28 |
| `g_co_hgic` | view | 8 | `indfrom` 1999-06-30 to 2026-11-19 |
| `g_co_iaudit` | view (empty) | 10 | `datadate`, not asked |
| `g_co_idesind` | view | 36 | `apdedateq`, not asked |
| `g_co_ifndq` | view | 879 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_co_ifndsa` | view | 453 | `datadate` 1980-06-30 to 2026-09-30 |
| `g_co_ifndytd` | view | 731 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_co_ifntq` | view | 444 | `datadate` 1980-03-31 to 2026-09-30 |
| `g_co_ifntsa` | view | 231 | `datadate` 1980-12-31 to 2026-09-30 |
| `g_co_ifntytd` | view | 379 | `datadate` 1982-06-30 to 2026-09-30 |
| `g_co_industry` | view | 8 | `datadate` 1980-09-30 to 2026-09-30 |
| `g_co_ipcd` | view | 5 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_co_offtitl` | view | 4 | - |
| `g_company` | view | 39 | `dldte` 1986-02-05 to 2026-11-17 |
| `g_currency` | view | 6 | `isocurbd` 1900-01-01 to 2024-04-30 |
| `g_ecind_desc` | view | 8 | - |
| `g_ecind_mth` | view | 55 | `datadate` 1981-01-31 to 2030-12-31 |
| `g_exrt_dly` | view | 5 | `datadate` 1982-02-01 to 2026-11-18 |
| `g_exrt_mth` | view | 22 | `datadate` 1982-01-31 to 2026-11-30 |
| `g_funda` | view | 444 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_funda_fncd` | view | 360 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_fundq` | view | 381 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_fundq_fncd` | view | 355 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_idx_daily` | view | 10 | `datadate` 1985-12-31 to 2026-11-18 |
| `g_idx_index` | view | 14 | - |
| `g_idx_mth` | view | 21 | `datadate` 1970-08-31 to 2026-10-31 |
| `g_idxcst_his` | view | 5 | `from`, not measured (query failed) |
| `g_indexcst_his` | view | 5 | `fromdate` 1987-12-31 to 2026-11-18 |
| `g_names` | view | 12 | - |
| `g_names_ix` | view | 7 | - |
| `g_names_ix_cst` | view | 15 | `from`, not measured (query failed) |
| `g_namesq` | view | 12 | - |
| `g_sec_adesind` | view | 10 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_adjfact` | view | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `g_sec_afnd` | view | 21 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_afnddc` | view | 21 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_afnt` | view | 21 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_divid` | view | 35 | `anncdate` 1984-01-03 to 2027-03-21 |
| `g_sec_dprc` | view | 17 | `datadate` 1983-12-30 to 2026-11-18 |
| `g_sec_dtrt` | view | 6 | `datadate` 1984-01-02 to 2026-11-18 |
| `g_sec_gmdivfn` | view | 5 | `datadate` 2007-01-31 to 2026-10-31 |
| `g_sec_gmth` | view | 6 | `datadate` 2007-01-31 to 2026-10-31 |
| `g_sec_gmthdiv` | view | 6 | `datadate` 2007-01-31 to 2026-10-31 |
| `g_sec_gmthprc` | view | 8 | `datadate` 2007-01-31 to 2026-10-31 |
| `g_sec_history` | view | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `g_sec_idesind` | view | 10 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_sec_ifnd` | view | 62 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_sec_ifnt` | view | 35 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_sec_split` | view | 5 | `datadate` 1913-07-24 to 2026-11-18 |
| `g_secd` | view | 54 | `datadate` 1913-07-24 to 2028-12-01 |
| `g_secm` | view | 25 | `datadate` 2007-01-31 to 2026-10-31 |
| `g_secnamesd` | view | 8 | - |
| `g_security` | view | 15 | `dldtei` 1986-02-05 to 2026-11-18 |
| `g_sedolgvkey` | view | 3 | - |
| `g_tmptable_pkg6775_tbl5551` | view | 6 | `fromdate` 2026-11-18 to 2026-11-18 |
| `gsecnamesm` | view | 10 | `year1` 2007-01-31 to 2026-07-31 |
| `idx_ann` | view | 71 | `datadate` 1990-12-31 to 2025-12-31 |
| `idx_anndes` | view | 5 | `datadate` 1990-12-31 to 2027-12-31 |
| `idx_daily` | view | 10 | `datadate` 1978-12-29 to 2026-11-18 |
| `idx_index` | view | 14 | - |
| `idx_mth` | view | 21 | `datadate` 1962-01-31 to 2026-10-31 |
| `idx_qrt` | view | 57 | `datadate` 1984-03-31 to 2026-06-30 |
| `idx_qrtdes` | view | 6 | `datadate` 1984-03-31 to 2026-06-30 |
| `idxcst_his` | view | 5 | `from`, not measured (query failed) |
| `indexcst_his` | view | 5 | `fromdate` 1964-03-31 to 2026-11-19 |
| `io_qaggregate` | view | 13 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qbuysell` | view | 15 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qchanges` | view | 13 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qfloatadj` | view | 7 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qholders` | view | 10 | `datadate` 2004-03-31 to 2026-06-30 |
| `it_mbuysell` | view | 16 | `datadate` 2025-11-30 to 2026-12-31 |
| `it_msummary` | view | 21 | `datadate` 2026-11-10 to 2026-11-10 |
| `it_r_rltn` | view | 2 | - |
| `names` | view | 11 | - |
| `names_aco_indsta` | view | 7 | - |
| `names_aco_indstq` | view | 7 | - |
| `names_aco_pnfnda` | view | 7 | - |
| `names_aco_pnfndq` | view | 7 | - |
| `names_adsprate` | view | 7 | - |
| `names_ix` | view | 7 | - |
| `names_ix_cst` | view | 13 | `from`, not measured (query failed) |
| `names_seg` | view | 9 | - |
| `namesd` | view | 10 | - |
| `namesm` | view | 12 | `year1` 1962-01-31 to 2026-11-30 |
| `namesq` | view | 11 | - |
| `r_accstd` | view | 2 | - |
| `r_acqmeth` | view | 2 | - |
| `r_auditors` | view | 2 | - |
| `r_auopic` | view | 2 | - |
| `r_balpres` | view | 2 | - |
| `r_cf_formt` | view | 2 | - |
| `r_co_status` | view | 2 | - |
| `r_coindpre` | view | 2 | - |
| `r_compstat` | view | 2 | - |
| `r_consol` | view | 2 | - |
| `r_country` | view | 2 | - |
| `r_cstclscd` | view | 3 | - |
| `r_datacode` | view | 2 | - |
| `r_datafmt` | view | 2 | - |
| `r_divtaxmarker` | view | 2 | - |
| `r_docsrce` | view | 2 | - |
| `r_ex_codes` | view | 2 | - |
| `r_exchgtier` | view | 3 | - |
| `r_exrt_typ` | view | 2 | - |
| `r_fndfntcd` | view | 3 | - |
| `r_footnts` | view | 2 | - |
| `r_foricd` | view | 3 | - |
| `r_giccd` | view | 4 | - |
| `r_hcalendr` | view | 2 | `datadate` 1982-12-30 to 2030-12-31 |
| `r_idxclscd` | view | 3 | - |
| `r_inactvcd` | view | 2 | - |
| `r_incstats` | view | 2 | - |
| `r_indfmt` | view | 2 | - |
| `r_indsec` | view | 2 | - |
| `r_invval` | view | 2 | - |
| `r_issuetyp` | view | 2 | - |
| `r_majidxcl` | view | 3 | - |
| `r_mic_codes` | view | 2 | - |
| `r_naiccd` | view | 3 | - |
| `r_notetype` | view | 2 | - |
| `r_ntsubtype` | view | 3 | - |
| `r_offcrso` | view | 2 | - |
| `r_ogmethod` | view | 2 | - |
| `r_opinions` | view | 2 | - |
| `r_prc_stat` | view | 2 | - |
| `r_qsrcdoc` | view | 2 | - |
| `r_sec_stat` | view | 2 | - |
| `r_secannfn` | view | 2 | - |
| `r_sectors` | view | 2 | - |
| `r_siccd` | view | 3 | - |
| `r_spiicd` | view | 3 | - |
| `r_spmicd` | view | 3 | - |
| `r_statalrt` | view | 2 | - |
| `r_states` | view | 2 | - |
| `r_stko` | view | 2 | - |
| `r_titles` | view | 2 | - |
| `r_updates` | view | 2 | - |
| `sec_adesind` | view | 10 | `datadate` 1982-06-30 to 2027-05-31 |
| `sec_adjfact` | view | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `sec_afnd` | view | 21 | `datadate` 1982-06-30 to 2027-05-31 |
| `sec_afnddc` | view | 21 | `datadate` 1982-06-30 to 2027-05-31 |
| `sec_afnt` | view | 21 | `datadate` 1998-06-30 to 2026-10-31 |
| `sec_divid` | view | 35 | `anncdate` 1988-10-09 to 2026-11-18 |
| `sec_dprc` | view | 17 | `datadate` 1983-12-30 to 2026-11-18 |
| `sec_dtrt` | view | 6 | `datadate` 1984-01-02 to 2026-11-18 |
| `sec_history` | view | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `sec_idcurrent` | view | 4 | - |
| `sec_idesind` | view | 10 | `datadate` 1981-03-31 to 2026-10-31 |
| `sec_idhist` | view | 6 | `efffrom` 1900-01-01 to 2028-12-15 |
| `sec_ifnd` | view | 62 | `datadate` 2005-04-30 to 2026-10-31 |
| `sec_ifnt` | view | 35 | `datadate` 2005-09-30 to 2026-10-31 |
| `sec_mdivfn` | view | 14 | `datadate` 1968-07-31 to 2026-11-30 |
| `sec_mshare` | view | 9 | `datadate` 1998-04-30 to 2026-10-31 |
| `sec_msptfn` | view | 14 | `datadate` 1982-04-30 to 2016-07-31 |
| `sec_mth` | view | 10 | `datadate` 1962-01-31 to 2026-12-31 |
| `sec_mthdiv` | view | 8 | `datadate` 1962-01-31 to 2026-12-31 |
| `sec_mthprc` | view | 10 | `datadate` 1962-01-31 to 2026-11-30 |
| `sec_mthspt` | view | 5 | `datadate` 1962-01-31 to 2026-11-30 |
| `sec_mthtrt` | view | 5 | `datadate` 1962-01-31 to 2026-10-31 |
| `sec_shortint` | view | 6 | `datadate` 2006-07-14 to 2026-11-13 |
| `sec_shortint_legacy` | view | 6 | `datadate` 1973-01-15 to 2024-12-31 |
| `sec_spind` | view | 11 | `datadate` 1990-01-02 to 2002-01-02 |
| `sec_split` | view | 5 | `datadate` 1969-05-21 to 2026-11-18 |
| `secd` | view | 43 | `datadate` 1983-12-30 to 2027-11-12 |
| `secm` | view | 45 | `datadate` 1962-01-31 to 2026-12-31 |
| `security` | view | 16 | `dldtei` 1900-01-01 to 2026-11-18 |
| `sedolgvkey` | view | 3 | - |
| `seg_ann` | view | 7 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_annfund` | view | 79 | `datadate` 2018-06-30 to 2026-09-30 |
| `seg_customer` | view | 10 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_geo` | view | 6 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_naics` | view | 7 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_product` | view | 8 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_type` | view | 8 | `datadate` 2020-06-30 to 2026-09-30 |
| `spidx_cst` | view (empty) | 11 | `datadate`, not asked |
| `spind` | view | 5 | - |
| `spind_dly` | view | 7 | `datadate` 1988-01-04 to 2002-03-22 |
| `spind_mth` | view | 3 | `datadate` 1990-01-31 to 2001-12-31 |
| `wrds_g_exrate` | view | 7 | `datadate` 1982-02-01 to 2026-11-18 |
| `wrds_idx_cst_current` | view | 12 | `fromdate` 2009-12-18 to 2026-11-09 |
| `wrds_ratios` | view | 95 | `adate` 1961-06-30 to 2026-08-31 |
| `wrds_seg_customer` | view | 10 | `srcdate` 2020-06-30 to 2026-09-30 |
| `wrds_seg_geo` | view | 6 | `srcdate` 2020-06-30 to 2026-09-30 |
| `wrds_seg_product` | view | 8 | `srcdate` 2020-06-30 to 2026-09-30 |
| `wrds_segmerged` | view | 92 | `datadate` 2018-06-30 to 2026-09-30 |
| `xfl_column` | view | 15 | - |
| `xfl_table` | view | 6 | - |

## comp_bank_daily

| table | rows | columns | dates |
|---|---|---|---|
| `bank_aacctchg` | 4,506 | 8 | `datadate` 2007-12-31 to 2024-09-30 |
| `bank_adesind` | 72,974 | 29 | `apdedate` 2003-06-30 to 2026-09-30 |
| `bank_afnd1` | 62,903 | 235 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_afnd2` | 40,557 | 200 | `datadate` 1955-12-31 to 2026-09-30 |
| `bank_afnddc1` | 34,107 | 235 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_afnddc2` | 34,125 | 200 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_afntind` | 33,101 | 430 | `datadate` 1959-12-31 to 2026-09-30 |
| `bank_funda` | 72,974 | 465 | `apdedate` 2003-06-30 to 2026-09-30 |
| `bank_funda_fncd` | 37,397 | 409 | `datadate` 1958-12-31 to 2026-09-30 |
| `bank_fundq` | 273,986 | 559 | `apdedateq` 2002-09-30 to 2026-09-30 |
| `bank_fundq_fncd` | 273,986 | 629 | `datadate` 1961-12-31 to 2026-09-30 |
| `bank_iacctchg` | 5,016 | 9 | `datadate` 2007-03-31 to 2024-03-31 |
| `bank_idesind` | 273,986 | 35 | `apdedateq` 2002-09-30 to 2026-09-30 |
| `bank_ifndq` | 152,297 | 613 | `datadate` 1961-12-31 to 2026-09-30 |
| `bank_ifndytd` | 118,251 | 423 | `datadate` 1962-03-31 to 2026-09-30 |
| `bank_ifntq` | 138,953 | 310 | `datadate` 1961-12-31 to 2026-09-30 |
| `bank_ifntytd` | 86,774 | 215 | `datadate` 1962-03-31 to 2026-09-30 |
| `bank_names` | 2,422 | 11 | - |
| `bank_namesq` | 2,417 | 11 | - |
| `chars` | view (empty) | 39 | - |

## comp_execucomp

| table | rows | columns | dates |
|---|---|---|---|
| `anncomp` | 383,382 | 107 | `becameceo` 1945-01-01 to 2026-10-26 |
| `codirfin` | 144,636 | 71 | `srcdate` 1992-03-31 to 2026-09-29 |
| `colev` | 4,254 | 18 | - |
| `coperol` | 73,601 | 14 | `becameceo` 1945-01-01 to 2026-10-26 |
| `deferredcomp` | 120,377 | 46 | `becameceo` 1960-01-01 to 2026-10-26 |
| `directorcomp` | 362,097 | 28 | - |
| `ex_black` | view | 6 | - |
| `ex_header` | 73,657 | 38 | `becameceo` 1945-01-01 to 2026-10-26 |
| `exnames` | 4,250 | 5 | - |
| `ltawdtab` | 24,010 | 48 | `becameceo` 1950-01-01 to 2025-07-14 |
| `outstandingawards` | 1,363,322 | 50 | `exdate` 1930-01-02 to 2044-04-21 |
| `pension` | 114,270 | 44 | `becameceo` 1951-01-01 to 2026-10-26 |
| `person` | 64,783 | 8 | - |
| `planbasedawards` | 601,598 | 53 | `grant_date` 1905-07-07 to 2406-10-01 |
| `stgrttab` | 132,620 | 49 | `exdate` 1992-10-01 to 2025-12-16 |

## comp_global_daily

| table | rows | columns | dates |
|---|---|---|---|
| `dd_group` | 1,846 | 5 | - |
| `dd_group_xref` | 67,457 | 3 | - |
| `dd_item` | 12,006 | 15 | - |
| `dd_package` | view | 4 | - |
| `g_chars` | view (empty) | 44 | - |
| `g_co_aaudit` | 1,102,473 | 12 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_adesind` | 1,095,296 | 33 | `apdedate`, not asked |
| `g_co_afnd1` | 1,095,240 | 512 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afnd2` | 1,095,224 | 465 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afnddc1` | 801,322 | 512 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afnddc2` | 1,010,666 | 465 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afntind1` | 906,375 | 512 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_afntind2` | 511,296 | 465 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_ainvval` | 741,665 | 8 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_co_gsuppl` | 1,071,967 | 153 | `auopdate` 1991-02-25 to 2008-08-28 |
| `g_co_hgic` | 90,113 | 8 | `indfrom` 1999-06-30 to 2026-11-19 |
| `g_co_iaudit` | view (empty) | 10 | `datadate`, not asked |
| `g_co_idesind` | 4,174,423 | 36 | `apdedateq`, not asked |
| `g_co_ifndq` | 4,025,539 | 879 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_co_ifndsa` | 2,079,493 | 453 | `datadate` 1980-06-30 to 2026-09-30 |
| `g_co_ifndytd` | 4,096,196 | 731 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_co_ifntq` | 3,029,392 | 444 | `datadate` 1980-03-31 to 2026-09-30 |
| `g_co_ifntsa` | 1,654,637 | 231 | `datadate` 1980-12-31 to 2026-09-30 |
| `g_co_ifntytd` | 2,757,233 | 379 | `datadate` 1982-06-30 to 2026-09-30 |
| `g_co_industry` | 1,065,482 | 8 | `datadate` 1980-09-30 to 2026-09-30 |
| `g_co_ipcd` | 196,473 | 5 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_co_offtitl` | 72,372 | 4 | - |
| `g_company` | 84,405 | 39 | `dldte` 1986-02-05 to 2026-11-17 |
| `g_currency` | view | 6 | `isocurbd` 1900-01-01 to 2024-04-30 |
| `g_ecind_desc` | 1,199 | 8 | - |
| `g_ecind_mth` | 34,200 | 55 | `datadate` 1981-01-31 to 2030-12-31 |
| `g_exrt_dly` | 2,240,108 | 5 | `datadate` 1982-02-01 to 2026-11-18 |
| `g_exrt_mth` | 76,446 | 22 | `datadate` 1982-01-31 to 2026-11-30 |
| `g_funda` | 1,095,391 | 444 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_funda_fncd` | 1,095,391 | 360 | `datadate` 1987-06-30 to 2026-09-30 |
| `g_fundq` | 4,174,425 | 381 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_fundq_fncd` | 4,174,425 | 355 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_idx_daily` | 4,281,820 | 10 | `datadate` 1985-12-31 to 2026-11-18 |
| `g_idx_index` | 735 | 14 | - |
| `g_idx_mth` | 200,564 | 21 | `datadate` 1970-08-31 to 2026-10-31 |
| `g_idxcst_his` | 23,852 | 5 | `from`, not measured (query failed) |
| `g_indexcst_his` | 2,738 | 5 | `fromdate` 1987-12-31 to 2026-11-18 |
| `g_names` | 62,873 | 12 | - |
| `g_names_ix` | 735 | 7 | - |
| `g_names_ix_cst` | 24,541 | 15 | `from`, not measured (query failed) |
| `g_namesq` | 60,620 | 12 | - |
| `g_sec_adesind` | 1,111,044 | 10 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_adjfact` | 391,324 | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `g_sec_afnd` | 1,081,724 | 21 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_afnddc` | 1,081,724 | 21 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_afnt` | 834,014 | 21 | `datadate` 1979-01-31 to 2026-09-30 |
| `g_sec_divid` | 1,138,522 | 35 | `anncdate` 1984-01-03 to 2027-03-21 |
| `g_sec_dprc` | 320,290,944 | 17 | `datadate`, not asked (too big) |
| `g_sec_dtrt` | 1,173,150 | 6 | `datadate` 1984-01-02 to 2026-11-18 |
| `g_sec_gmdivfn` | 10,943,732 | 5 | `datadate`, not asked (too big) |
| `g_sec_gmth` | 10,943,732 | 6 | `datadate`, not asked (too big) |
| `g_sec_gmthdiv` | 10,943,732 | 6 | `datadate`, not asked (too big) |
| `g_sec_gmthprc` | 10,943,732 | 8 | `datadate`, not asked (too big) |
| `g_sec_history` | 182,351 | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `g_sec_idesind` | 3,786,839 | 10 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_sec_ifnd` | 3,746,281 | 62 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_sec_ifnt` | 3,109,474 | 35 | `datadate` 1979-03-31 to 2026-09-30 |
| `g_sec_split` | 123,227 | 5 | `datadate` 1913-07-24 to 2026-11-18 |
| `g_secd` | 320,421,248 | 54 | `datadate`, not asked (too big) |
| `g_secm` | 10,943,732 | 25 | `datadate`, not asked (too big) |
| `g_secnamesd` | 130,804 | 8 | - |
| `g_security` | 135,636 | 15 | `dldtei` 1986-02-05 to 2026-11-18 |
| `g_sedolgvkey` | 168,616 | 3 | - |
| `g_tmptable_pkg6775_tbl5551` | view | 6 | `fromdate` 2026-11-18 to 2026-11-18 |
| `gsecnamesm` | 81,307 | 10 | `year1` 2007-01-31 to 2026-07-31 |
| `r_accstd` | view | 2 | - |
| `r_acqmeth` | view | 2 | - |
| `r_auditors` | view | 2 | - |
| `r_auopic` | view | 2 | - |
| `r_balpres` | view | 2 | - |
| `r_cf_formt` | view | 2 | - |
| `r_co_status` | view | 2 | - |
| `r_coindpre` | view | 2 | - |
| `r_compstat` | view | 2 | - |
| `r_consol` | view | 2 | - |
| `r_country` | view | 2 | - |
| `r_cstclscd` | view | 3 | - |
| `r_datacode` | view | 2 | - |
| `r_datafmt` | view | 2 | - |
| `r_divtaxmarker` | view | 2 | - |
| `r_docsrce` | view | 2 | - |
| `r_ex_codes` | view | 2 | - |
| `r_exchgtier` | view | 3 | - |
| `r_exrt_typ` | view | 2 | - |
| `r_fndfntcd` | view | 3 | - |
| `r_footnts` | view | 2 | - |
| `r_foricd` | view | 3 | - |
| `r_giccd` | view | 4 | - |
| `r_hcalendr` | 48,491 | 2 | `datadate` 1982-12-30 to 2030-12-31 |
| `r_idxclscd` | 6,659 | 3 | - |
| `r_inactvcd` | view | 2 | - |
| `r_incstats` | view | 2 | - |
| `r_indfmt` | view | 2 | - |
| `r_indsec` | view | 2 | - |
| `r_invval` | view | 2 | - |
| `r_issuetyp` | view | 2 | - |
| `r_majidxcl` | view | 3 | - |
| `r_mic_codes` | view | 2 | - |
| `r_naiccd` | 2,719 | 3 | - |
| `r_notetype` | view | 2 | - |
| `r_ntsubtype` | view | 3 | - |
| `r_offcrso` | view | 2 | - |
| `r_ogmethod` | view | 2 | - |
| `r_opinions` | view | 2 | - |
| `r_prc_stat` | view | 2 | - |
| `r_qsrcdoc` | view | 2 | - |
| `r_sec_stat` | view | 2 | - |
| `r_secannfn` | view | 2 | - |
| `r_sectors` | view | 2 | - |
| `r_siccd` | 1,759 | 3 | - |
| `r_spiicd` | view | 3 | - |
| `r_spmicd` | view | 3 | - |
| `r_statalrt` | view | 2 | - |
| `r_states` | view | 2 | - |
| `r_stko` | view | 2 | - |
| `r_titles` | view | 2 | - |
| `r_updates` | view | 2 | - |
| `wrds_g_exrate` | 2,240,108 | 7 | `datadate` 1982-02-01 to 2026-11-18 |
| `xfl_column` | 21,276 | 15 | - |
| `xfl_table` | view | 6 | - |

## comp_na_daily_all

| table | rows | columns | dates |
|---|---|---|---|
| `aco_amda` | 70,488 | 10 | `datadate` 1973-12-31 to 2027-05-31 |
| `aco_imda` | 34,647 | 11 | `datadate` 1994-03-31 to 2026-09-30 |
| `aco_indfnta` | 20,344 | 446 | `datadate` 1951-12-31 to 2026-09-30 |
| `aco_indfntq` | 56,547 | 274 | `datadate` 1962-03-31 to 2026-09-30 |
| `aco_indfntytd` | 8,026 | 172 | `datadate` 1962-03-31 to 2026-09-30 |
| `aco_indsta` | 59,382 | 886 | `datadate` 1951-08-31 to 2026-09-30 |
| `aco_indstq` | 221,345 | 541 | `datadate` 1962-02-28 to 2026-10-31 |
| `aco_indstytd` | 195,567 | 337 | `datadate` 1962-02-28 to 2026-10-31 |
| `aco_notesa` | 10,683,081 | 12 | `datadate`, not asked (too big) |
| `aco_notesq` | 11,600,515 | 13 | `datadate`, not asked (too big) |
| `aco_notessa` | 790,406 | 13 | `datadate` 1999-01-31 to 2026-11-30 |
| `aco_notesytd` | 5,637,064 | 13 | `datadate`, not asked (too big) |
| `aco_pnfnda` | 155,403 | 164 | `datadate` 1973-06-30 to 2026-09-30 |
| `aco_pnfndq` | 645,685 | 21 | `datadate` 1996-07-31 to 2026-10-31 |
| `aco_pnfndytd` | 645,837 | 21 | `datadate` 1996-07-31 to 2026-10-31 |
| `aco_pnfnta` | 30,413 | 85 | `datadate` 1985-12-31 to 2026-09-30 |
| `aco_pnfntq` | 3,171 | 14 | `datadate` 2006-06-30 to 2026-09-30 |
| `aco_pnfntytd` | 1,490 | 14 | `datadate` 2007-03-31 to 2026-03-31 |
| `aco_transa` | 47,241,824 | 15 | `datadate`, not asked (too big) |
| `aco_transq` | 76,057,200 | 16 | `datadate`, not asked (too big) |
| `aco_transsa` | 5,002,014 | 16 | `datadate`, not asked (too big) |
| `aco_transytd` | 29,983,964 | 16 | `datadate`, not asked (too big) |
| `adsprate` | 3,023,652 | 5 | `datadate` 1978-11-30 to 2017-02-28 |
| `asec_amda` | view (empty) | 12 | `datadate`, not asked |
| `asec_imda` | 11 | 12 | `datadate` 2011-03-31 to 2018-03-31 |
| `asec_notesa` | 2,477 | 14 | `datadate` 1999-06-30 to 2026-06-30 |
| `asec_notesq` | 26,189 | 14 | `datadate` 2004-12-31 to 2026-09-30 |
| `asec_transa` | 934 | 17 | `datadate` 2007-12-31 to 2026-09-30 |
| `asec_transq` | 3,213 | 17 | `datadate` 2008-03-31 to 2026-09-30 |
| `chars` | view (empty) | 360 | - |
| `co_aacctchg` | 23,371 | 8 | `datadate` 2007-06-30 to 2026-06-30 |
| `co_aaudit` | 459,071 | 12 | `datadate` 1964-12-31 to 2027-05-31 |
| `co_acthist` | 56,842 | 20 | `datadate` 1988-01-20 to 2026-11-18 |
| `co_adesind` | 942,949 | 33 | `apdedate` 2002-12-31 to 2026-10-25 |
| `co_adjfact` | 156,001 | 5 | `effdate` 1900-01-01 to 2026-11-18 |
| `co_afnd1` | 844,490 | 539 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afnd2` | 773,387 | 468 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afnddc1` | 495,395 | 539 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afnddc2` | 574,890 | 468 | `datadate` 1950-06-30 to 2026-10-31 |
| `co_afntind1` | 510,575 | 539 | `datadate` 1950-12-31 to 2026-10-31 |
| `co_afntind2` | 407,573 | 468 | `datadate` 1950-12-31 to 2027-05-31 |
| `co_ainvval` | 534,154 | 8 | `datadate` 1950-06-30 to 2026-09-30 |
| `co_amkt` | 1,543,617 | 14 | `datadate` 1950-06-30 to 2027-05-31 |
| `co_busdescl` | 57,261 | 2 | - |
| `co_cotype` | 47,163 | 4 | `effdate` 1900-01-01 to 2026-11-13 |
| `co_filedate` | 2,669,613 | 7 | `datadate` 1966-08-31 to 2026-10-31 |
| `co_fortune` | 35,650 | 5 | `datadate` 1982-12-31 to 2025-12-31 |
| `co_hgic` | 46,006 | 8 | `indfrom` 1999-06-30 to 2026-11-18 |
| `co_iacctchg` | 22,642 | 9 | `datadate` 2007-02-28 to 2026-07-31 |
| `co_iaudit` | 843,003 | 10 | `datadate` 2002-03-31 to 2027-05-31 |
| `co_idesind` | 2,149,204 | 36 | `apdedateq` 2002-03-31 to 2026-11-01 |
| `co_ifndq` | 2,129,004 | 937 | `datadate` 1961-03-31 to 2026-10-31 |
| `co_ifndsa` | 437,013 | 463 | `datadate` 1965-06-30 to 2026-10-31 |
| `co_ifndytd` | 1,763,511 | 741 | `datadate` 1961-03-31 to 2026-10-31 |
| `co_ifntq` | 1,689,834 | 473 | `datadate` 1961-07-31 to 2027-05-31 |
| `co_ifntsa` | 259,848 | 236 | `datadate` 1985-06-30 to 2026-10-31 |
| `co_ifntytd` | 1,221,577 | 384 | `datadate` 1961-07-31 to 2026-10-31 |
| `co_imkt` | 5,506,861 | 15 | `datadate`, not asked (too big) |
| `co_industry` | 373,262 | 8 | `datadate` 1950-12-31 to 2026-09-30 |
| `co_ipcd` | 52,942 | 5 | `datadate` 1955-12-31 to 2026-09-30 |
| `co_mthly` | 4,178,180 | 4 | `datadate` 1978-11-30 to 2026-10-31 |
| `co_offtitl` | 239,709 | 4 | - |
| `company` | 58,813 | 40 | `dldte` 1964-01-10 to 2026-11-16 |
| `currency` | view | 6 | `isocurbd` 1900-01-01 to 2024-04-30 |
| `dd_group` | 1,943 | 5 | - |
| `dd_group_xref` | 68,858 | 3 | - |
| `dd_item` | 12,229 | 15 | - |
| `dd_package` | view | 4 | - |
| `ecind_desc` | view | 8 | - |
| `ecind_mth` | 1,200 | 55 | `datadate` 1981-01-31 to 2030-12-31 |
| `exrt_dly` | 2,240,108 | 5 | `datadate` 1982-02-01 to 2026-11-18 |
| `exrt_mth` | 76,446 | 22 | `datadate` 1982-01-31 to 2026-11-30 |
| `funda` | 942,949 | 949 | `datadate` 1950-06-30 to 2027-05-31 |
| `funda_fncd` | 942,949 | 888 | `datadate` 1950-06-30 to 2027-05-31 |
| `fundq` | 2,149,204 | 648 | `datadate` 1961-03-31 to 2027-05-31 |
| `fundq_fncd` | 2,149,204 | 778 | `datadate` 1961-03-31 to 2027-05-31 |
| `idx_ann` | 26,913 | 71 | `datadate` 1990-12-31 to 2025-12-31 |
| `idx_anndes` | 30,065 | 5 | `datadate` 1990-12-31 to 2027-12-31 |
| `idx_daily` | 8,771,503 | 10 | `datadate`, not asked (too big) |
| `idx_index` | 2,257 | 14 | - |
| `idx_mth` | 596,735 | 21 | `datadate` 1962-01-31 to 2026-10-31 |
| `idx_qrt` | 109,327 | 57 | `datadate` 1984-03-31 to 2026-06-30 |
| `idx_qrtdes` | 109,624 | 6 | `datadate` 1984-03-31 to 2026-06-30 |
| `idxcst_his` | 24,364 | 5 | `from`, not measured (query failed) |
| `indexcst_his` | 23,709 | 5 | `fromdate` 1964-03-31 to 2026-11-19 |
| `io_qaggregate` | 156,953 | 13 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qbuysell` | 1,517,451 | 15 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qchanges` | 919,829 | 13 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qfloatadj` | 36,499 | 7 | `datadate` 2004-03-31 to 2026-06-30 |
| `io_qholders` | 962,261 | 10 | `datadate` 2004-03-31 to 2026-06-30 |
| `it_mbuysell` | 159,003 | 16 | `datadate` 2025-11-30 to 2026-12-31 |
| `it_msummary` | 21,352 | 21 | `datadate` 2026-11-10 to 2026-11-10 |
| `it_r_rltn` | view | 2 | - |
| `names` | 47,239 | 11 | - |
| `names_aco_indsta` | 4,220 | 7 | - |
| `names_aco_indstq` | 4,598 | 7 | - |
| `names_aco_pnfnda` | 12,141 | 7 | - |
| `names_aco_pnfndq` | 20,775 | 7 | - |
| `names_adsprate` | 25,987 | 7 | - |
| `names_ix` | 2,257 | 7 | - |
| `names_ix_cst` | 2,908 | 13 | `from`, not measured (query failed) |
| `names_seg` | 8,137 | 9 | - |
| `namesd` | 66,908 | 10 | - |
| `namesm` | 64,334 | 12 | `year1` 1962-01-31 to 2026-11-30 |
| `namesq` | 47,015 | 11 | - |
| `r_accstd` | view | 2 | - |
| `r_acqmeth` | view | 2 | - |
| `r_auditors` | view | 2 | - |
| `r_auopic` | view | 2 | - |
| `r_balpres` | view | 2 | - |
| `r_cf_formt` | view | 2 | - |
| `r_co_status` | view | 2 | - |
| `r_coindpre` | view | 2 | - |
| `r_compstat` | view | 2 | - |
| `r_consol` | view | 2 | - |
| `r_country` | view | 2 | - |
| `r_cstclscd` | view | 3 | - |
| `r_datacode` | view | 2 | - |
| `r_datafmt` | view | 2 | - |
| `r_divtaxmarker` | view | 2 | - |
| `r_docsrce` | view | 2 | - |
| `r_ex_codes` | view | 2 | - |
| `r_exchgtier` | view | 3 | - |
| `r_exrt_typ` | view | 2 | - |
| `r_fndfntcd` | view | 3 | - |
| `r_footnts` | view | 2 | - |
| `r_foricd` | view | 3 | - |
| `r_giccd` | view | 4 | - |
| `r_hcalendr` | 61,593 | 2 | `datadate` 1982-12-30 to 2040-12-31 |
| `r_idxclscd` | 7,280 | 3 | - |
| `r_inactvcd` | view | 2 | - |
| `r_incstats` | view | 2 | - |
| `r_indfmt` | view | 2 | - |
| `r_indsec` | view | 2 | - |
| `r_invval` | view | 2 | - |
| `r_issuetyp` | view | 2 | - |
| `r_majidxcl` | view | 3 | - |
| `r_mic_codes` | view | 2 | - |
| `r_naiccd` | 2,919 | 3 | - |
| `r_notetype` | view | 2 | - |
| `r_ntsubtype` | view | 3 | - |
| `r_offcrso` | view | 2 | - |
| `r_ogmethod` | view | 2 | - |
| `r_opinions` | view | 2 | - |
| `r_prc_stat` | view | 2 | - |
| `r_qsrcdoc` | view | 2 | - |
| `r_sec_stat` | view | 2 | - |
| `r_secannfn` | view | 2 | - |
| `r_sectors` | view | 2 | - |
| `r_siccd` | 1,759 | 3 | - |
| `r_spiicd` | view | 3 | - |
| `r_spmicd` | view | 3 | - |
| `r_statalrt` | view | 2 | - |
| `r_states` | view | 2 | - |
| `r_stko` | view | 2 | - |
| `r_titles` | view | 2 | - |
| `r_updates` | view | 2 | - |
| `sec_adesind` | 448,277 | 10 | `datadate` 1982-06-30 to 2027-05-31 |
| `sec_adjfact` | 121,955 | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `sec_afnd` | 432,031 | 21 | `datadate` 1982-06-30 to 2027-05-31 |
| `sec_afnddc` | 432,031 | 21 | `datadate` 1982-06-30 to 2027-05-31 |
| `sec_afnt` | 550 | 21 | `datadate` 1998-06-30 to 2026-10-31 |
| `sec_divid` | 1,197,641 | 35 | `anncdate` 1988-10-09 to 2026-11-18 |
| `sec_dprc` | 162,352,896 | 17 | `datadate`, not asked (too big) |
| `sec_dtrt` | 1,214,193 | 6 | `datadate` 1984-01-02 to 2026-11-18 |
| `sec_history` | 335,772 | 6 | `effdate` 1900-01-01 to 2026-11-18 |
| `sec_idcurrent` | 509,525 | 4 | - |
| `sec_idesind` | 835,572 | 10 | `datadate` 1981-03-31 to 2026-10-31 |
| `sec_idhist` | 875,639 | 6 | `efffrom` 1900-01-01 to 2028-12-15 |
| `sec_ifnd` | 788,524 | 62 | `datadate` 2005-04-30 to 2026-10-31 |
| `sec_ifnt` | 33,557 | 35 | `datadate` 2005-09-30 to 2026-10-31 |
| `sec_mdivfn` | 90,262 | 14 | `datadate` 1968-07-31 to 2026-11-30 |
| `sec_mshare` | 6,023,791 | 9 | `datadate`, not asked (too big) |
| `sec_msptfn` | 5,940 | 14 | `datadate` 1982-04-30 to 2016-07-31 |
| `sec_mth` | 8,537,815 | 10 | `datadate`, not asked (too big) |
| `sec_mthdiv` | 3,315,762 | 8 | `datadate` 1962-01-31 to 2026-12-31 |
| `sec_mthprc` | 8,368,947 | 10 | `datadate`, not asked (too big) |
| `sec_mthspt` | 75,622 | 5 | `datadate` 1962-01-31 to 2026-11-30 |
| `sec_mthtrt` | 8,387,760 | 5 | `datadate`, not asked (too big) |
| `sec_shortint` | 5,429,348 | 6 | `datadate`, not asked (too big) |
| `sec_shortint_legacy` | 4,770,658 | 6 | `datadate` 1973-01-15 to 2024-12-31 |
| `sec_spind` | 2,882,384 | 11 | `datadate` 1990-01-02 to 2002-01-02 |
| `sec_split` | 43,777 | 5 | `datadate` 1969-05-21 to 2026-11-18 |
| `secd` | 162,441,024 | 43 | `datadate`, not asked (too big) |
| `secm` | 8,593,577 | 45 | `datadate`, not asked (too big) |
| `security` | 78,183 | 16 | `dldtei` 1900-01-01 to 2026-11-18 |
| `sedolgvkey` | 169,046 | 3 | - |
| `seg_ann` | 39,927 | 7 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_annfund` | 463,765 | 79 | `datadate` 2018-06-30 to 2026-09-30 |
| `seg_customer` | 150,403 | 10 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_geo` | 96,768 | 6 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_naics` | 199,499 | 7 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_product` | 189,285 | 8 | `datadate` 2020-06-30 to 2026-09-30 |
| `seg_type` | 164,165 | 8 | `datadate` 2020-06-30 to 2026-09-30 |
| `spidx_cst` | view (empty) | 11 | `datadate`, not asked |
| `spind` | 552 | 5 | - |
| `spind_dly` | 995,972 | 7 | `datadate` 1988-01-04 to 2002-03-22 |
| `spind_mth` | 54,931 | 3 | `datadate` 1990-01-31 to 2001-12-31 |
| `wrds_idx_cst_current` | 50,046 | 12 | `fromdate` 2009-12-18 to 2026-11-09 |
| `wrds_ratios` | 4,172,402 | 95 | `adate` 1961-06-30 to 2026-08-31 |
| `wrds_seg_customer` | 150,403 | 10 | `srcdate` 2020-06-30 to 2026-09-30 |
| `wrds_seg_geo` | 96,768 | 6 | `srcdate` 2020-06-30 to 2026-09-30 |
| `wrds_seg_product` | 189,285 | 8 | `srcdate` 2020-06-30 to 2026-09-30 |
| `wrds_segmerged` | 463,765 | 92 | `datadate` 2018-06-30 to 2026-09-30 |
| `xfl_column` | 21,276 | 15 | - |
| `xfl_table` | view | 6 | - |

## comp_segments_hist_daily

| table | rows | columns | dates |
|---|---|---|---|
| `names_seg` | 30,099 | 9 | - |
| `seg_ann` | 367,055 | 7 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_annfund` | 2,860,555 | 79 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_customer` | 736,191 | 10 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_geo` | 881,511 | 6 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_naics` | 1,419,407 | 7 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_product` | 758,434 | 8 | `datadate` 1994-09-30 to 2026-09-30 |
| `seg_type` | 1,436,257 | 8 | `datadate` 1976-06-30 to 2026-09-30 |
| `wrds_seg_customer` | 736,191 | 10 | `srcdate` 1976-06-30 to 2026-09-30 |
| `wrds_seg_geo` | 881,511 | 6 | `srcdate` 1976-06-30 to 2026-09-30 |
| `wrds_seg_product` | 758,434 | 8 | `srcdate` 1994-09-30 to 2026-09-30 |
| `wrds_segmerged` | 2,860,555 | 92 | `datadate` 1976-06-30 to 2026-09-30 |
| `xfl_column` | 21,276 | 15 | - |
| `xfl_table` | view | 6 | - |

## comp_snapshot

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 40 | - |
| `cs_items` | 4,505 | 2 | - |
| `csco_aaudit` | 1,561,049 | 6 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_afnd` | 129,872,736 | 6 | `effdate`, not asked (too big) |
| `csco_afntind` | 6,896,752 | 6 | `effdate`, not asked (too big) |
| `csco_ainvval` | 556,034 | 5 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_akey` | 1,157,828 | 13 | `datadate` 1968-06-30 to 2027-05-31 |
| `csco_atxt` | 11,003,279 | 6 | `effdate`, not asked (too big) |
| `csco_iaudit` | 2,218,421 | 6 | `effdate` 2002-10-24 to 2026-11-04 |
| `csco_ifndq` | 227,887,568 | 7 | `effdate`, not asked (too big) |
| `csco_ifndytd` | 131,716,560 | 7 | `effdate`, not asked (too big) |
| `csco_ifntq` | 23,729,816 | 7 | `effdate`, not asked (too big) |
| `csco_ifntytd` | 5,420,816 | 7 | `effdate`, not asked (too big) |
| `csco_ikey` | 2,166,027 | 16 | `datadate` 1973-09-30 to 2027-05-31 |
| `csco_ipcd` | view (empty) | 4 | `effdate`, not asked |
| `csco_itxt` | 31,769,834 | 6 | `effdate`, not asked (too big) |
| `cscompany` | 1,141,544 | 35 | `dldte` 1964-01-10 to 2026-10-22 |
| `cssecurity` | 1,607,589 | 16 | `dldtei` 1900-01-01 to 2026-11-04 |
| `dd_group` | 1,846 | 5 | - |
| `dd_group_xref` | 67,457 | 3 | - |
| `dd_item` | 12,006 | 15 | - |
| `dd_package` | view | 4 | - |
| `r_actioncd` | view | 2 | - |
| `sec_idhist` | 874,119 | 6 | `efffrom` 1900-01-01 to 2028-12-15 |
| `wrds_cs_names` | 323,593 | 43 | `begdate` 1986-12-14 to 2026-11-05 |
| `wrds_csa_pit` | 4,199,031 | 656 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_pit_dc` | 1,937,438 | 512 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_pit_dc_sorted` | 1,937,438 | 512 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_pit_sorted` | 4,198,659 | 656 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_restated` | 1,156,964 | 656 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csa_restated_dc` | 1,156,358 | 512 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csa_unrestated` | 1,156,964 | 656 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csa_unrestated_dc` | 1,156,358 | 512 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csq_pit` | 10,174,454 | 672 | `pitdate1`, not asked (too big) |
| `wrds_csq_pit_dc` | 4,491,670 | 516 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csq_pit_dc_sorted` | 4,491,670 | 516 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csq_pit_sorted` | 10,175,081 | 672 | `pitdate1`, not asked (too big) |
| `wrds_csq_restated` | 2,161,673 | 672 | `datadate` 1973-09-30 to 2027-05-31 |
| `wrds_csq_restated_dc` | 2,160,610 | 516 | `datadate` 1973-09-30 to 2027-05-31 |
| `wrds_csq_unrestated` | 2,162,065 | 672 | `datadate` 1973-09-30 to 2027-05-31 |
| `wrds_csq_unrestated_dc` | 2,160,610 | 516 | `datadate` 1973-09-30 to 2027-05-31 |
| `xfc_actionstartconditiontype` | view | 2 | - |
| `xfc_actionstatetype` | view | 2 | - |
| `xfc_actiontype` | view | 5 | - |
| `xfc_activitytype` | view | 2 | - |
| `xfc_changeflagtype` | view | 3 | - |
| `xfc_cleanuptype` | view | 3 | - |
| `xfc_column` | 28,282 | 3 | - |
| `xfc_columntodatabasetype` | 113,128 | 4 | - |
| `xfc_columnusetype` | view | 2 | - |
| `xfc_databasetype` | view | 2 | - |
| `xfc_datetimeformattype` | view | 3 | - |
| `xfc_datetimetodatabasetype` | view | 3 | - |
| `xfc_daynotinfeedfrequency` | view | 2 | - |
| `xfc_delimitertype` | view | 4 | - |
| `xfc_emailaccounttype` | view | 2 | - |
| `xfc_errormessage` | view (empty) | 5 | - |
| `xfc_failuretype` | view | 2 | - |
| `xfc_feedfrequencytype` | view | 3 | - |
| `xfc_feedpop` | view | 4 | - |
| `xfc_hosttype` | view | 3 | - |
| `xfc_indextype` | view | 4 | - |
| `xfc_lengthsemantictype` | view | 2 | - |
| `xfc_loaderobjecttype` | view | 2 | - |
| `xfc_loadersetting` | view | 5 | - |
| `xfc_loaderver` | view | 8 | `datereleased`, not asked |
| `xfc_loadjobtype` | view | 2 | - |
| `xfc_loadsubstatetype` | view | 2 | - |
| `xfc_loadsubtype` | view | 3 | - |
| `xfc_notificationtype` | view | 3 | - |
| `xfc_pac` | 3,378 | 6 | - |
| `xfc_pacgroup` | view | 4 | - |
| `xfc_pacsource` | view | 7 | - |
| `xfc_pacsourcetohost` | view | 12 | - |
| `xfc_pacsourcetype` | view | 3 | - |
| `xfc_pacver` | 3,602 | 13 | - |
| `xfc_pacverfeedpoptopacsrchost` | 9,455 | 7 | `expiredate` 2014-03-07 to 2026-09-30 |
| `xfc_pacverfeedpoptotableinst` | 18,990 | 6 | - |
| `xfc_pacverfeedpoptozipfile` | 12,573 | 4 | - |
| `xfc_pacverfeedpopupgrade` | view | 4 | - |
| `xfc_pacverrelationship` | 10,684 | 4 | - |
| `xfc_pacvertofeedpop` | 4,800 | 4 | - |
| `xfc_phasetype` | view | 2 | - |
| `xfc_prepostloadsql` | view (empty) | 6 | - |
| `xfc_prepostloadtype` | view | 3 | - |
| `xfc_progresstype` | view | 2 | - |
| `xfc_proxyprotocoltype` | view | 2 | - |
| `xfc_relationshiptype` | view | 3 | - |
| `xfc_resulttype` | view | 3 | - |
| `xfc_table` | 4,772 | 3 | - |
| `xfc_tableinst` | 5,525 | 4 | - |
| `xfc_tableinstindex` | 52,568 | 8 | - |
| `xfc_tableinstindexcolumn` | 119,469 | 5 | - |
| `xfc_tableinsttocolumn` | 81,833 | 6 | - |
| `xfc_tabletype` | view | 2 | - |
| `xfc_textfile` | 7,606 | 11 | - |
| `xfc_textfilecolumnmapping` | 295,690 | 6 | - |
| `xfc_textfiletype` | view | 2 | - |
| `xfc_upgradeabstraction` | view | 2 | - |
| `xfc_upgradetable` | 522 | 4 | - |
| `xfc_upgradetablesql` | view (empty) | 3 | - |
| `xfc_upgradetype` | view | 3 | - |
| `xfc_validationtype` | view | 3 | - |
| `xfc_zipfile` | 9,428 | 9 | - |
| `xfc_zipfiletotextfile` | 26,709 | 2 | - |
| `xfc_zipfiletype` | view | 2 | - |
| `xfc_zipruntype` | view | 4 | - |
| `xfl_column` | 21,276 | 15 | - |
| `xfl_datagroup` | 608 | 3 | - |
| `xfl_datagroup_table` | view | 2 | - |
| `xfl_db_version` | view | 1 | - |
| `xfl_file_datagroup` | 1,017 | 3 | - |
| `xfl_filelayout` | 2,065 | 7 | - |
| `xfl_lrm_cstat_fsup0` | view | 2 | - |
| `xfl_lrm_cstat_fsup0_2` | view | 4 | `loaddate` 2013-03-16 to 2013-03-17 |
| `xfl_lrm_cstat_rsup0` | view | 3 | - |
| `xfl_lrm_cstat_tsup0` | view | 4 | `loaddate` 2013-10-07 to 2013-10-07 |
| `xfl_lrm_user_load_plan` | view | 1 | - |
| `xfl_mapping` | view | 4 | - |
| `xfl_package` | view | 9 | - |
| `xfl_package_file` | 1,678 | 9 | - |
| `xfl_package_rel` | view | 4 | - |
| `xfl_refer` | view | 5 | - |
| `xfl_sequence` | view | 2 | - |
| `xfl_table` | view | 6 | - |

## compsamp

| table | rows | columns | dates |
|---|---|---|---|
| `company` | view | 39 | `dldte` 1987-12-31 to 2015-07-29 |
| `compsamp` | view | 36 | `date` 1985-01-01 to 2004-01-01 |
| `computext_global` | view | 21 | `documentdate` 2014-01-06 to 2025-12-31 |
| `computext_us` | view | 21 | `documentdate` 2014-01-02 to 2025-12-31 |
| `funda` | view | 948 | `datadate` 1950-09-30 to 2020-09-30 |
| `funda_fncd` | view | 883 | `datadate` 1950-09-30 to 2020-09-30 |
| `fundq` | view | 647 | `datadate` 1961-12-31 to 2020-12-31 |
| `fundq_fncd` | view | 777 | `datadate` 1961-12-31 to 2020-12-31 |
| `names` | view | 11 | - |
| `namesq` | view | 11 | - |
| `secd` | view | 43 | `datadate` 1983-12-30 to 2021-03-12 |
| `secm` | view | 45 | `datadate` 1962-01-31 to 2021-01-31 |
| `wrds_segmerged` | view | 92 | `datadate` 2012-06-30 to 2020-09-30 |

## compsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `company` | 25 | 39 | `dldte` 1987-12-31 to 2015-07-29 |
| `compsamp` | 10,000 | 36 | `date` 1985-01-01 to 2004-01-01 |
| `funda` | 1,224 | 948 | `datadate` 1950-09-30 to 2020-09-30 |
| `funda_fncd` | 1,224 | 883 | `datadate` 1950-09-30 to 2020-09-30 |
| `fundq` | 3,168 | 647 | `datadate` 1961-12-31 to 2020-12-31 |
| `fundq_fncd` | 3,168 | 777 | `datadate` 1961-12-31 to 2020-12-31 |
| `names` | 25 | 11 | - |
| `namesq` | 25 | 11 | - |
| `secd` | 142,468 | 43 | `datadate` 1983-12-30 to 2021-03-12 |
| `secm` | 9,332 | 45 | `datadate` 1962-01-31 to 2021-01-31 |
| `wrds_segmerged` | 1,227 | 92 | `datadate` 2012-06-30 to 2020-09-30 |

## compsamp_computext

| table | rows | columns | dates |
|---|---|---|---|
| `computext_global` | 603,375 | 21 | `documentdate` 2014-01-06 to 2025-12-31 |
| `computext_us` | 2,188,331 | 21 | `documentdate` 2014-01-02 to 2025-12-31 |

## compsamp_snapshot

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 40 | - |
| `wrds_cs_names` | 15,643 | 13 | `begdate` 1986-12-14 to 2015-04-28 |
| `wrds_csa_pit` | 239,299 | 579 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csa_pit_sorted` | 239,299 | 579 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csa_restated` | 62,763 | 579 | `datadate` 1968-12-31 to 2015-03-31 |
| `wrds_csa_unrestated` | 62,763 | 579 | `datadate` 1968-12-31 to 2015-03-31 |
| `wrds_csq_pit` | 607,568 | 620 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csq_pit_sorted` | 607,568 | 620 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csq_restated` | 104,204 | 620 | `datadate` 1973-09-30 to 2015-03-31 |
| `wrds_csq_unrestated` | 104,204 | 620 | `datadate` 1973-09-30 to 2015-03-31 |

## compseg

| table | rows | columns | dates |
|---|---|---|---|
| `names_seg` | view | 9 | - |
| `seg_ann` | view | 7 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_annfund` | view | 79 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_customer` | view | 10 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_geo` | view | 6 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_naics` | view | 7 | `datadate` 1976-06-30 to 2026-09-30 |
| `seg_product` | view | 8 | `datadate` 1994-09-30 to 2026-09-30 |
| `seg_type` | view | 8 | `datadate` 1976-06-30 to 2026-09-30 |
| `wrds_seg_customer` | view | 10 | `srcdate` 1976-06-30 to 2026-09-30 |
| `wrds_seg_geo` | view | 6 | `srcdate` 1976-06-30 to 2026-09-30 |
| `wrds_seg_product` | view | 8 | `srcdate` 1994-09-30 to 2026-09-30 |
| `wrds_segmerged` | view | 92 | `datadate` 1976-06-30 to 2026-09-30 |
| `xfl_column` | view | 15 | - |
| `xfl_table` | view | 6 | - |

## compsnap

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 40 | - |
| `cs_items` | view | 2 | - |
| `csco_aaudit` | view | 6 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_afnd` | view | 6 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_afntind` | view | 6 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_ainvval` | view | 5 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_akey` | view | 13 | `datadate` 1968-06-30 to 2027-05-31 |
| `csco_atxt` | view | 6 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_iaudit` | view | 6 | `effdate` 2002-10-24 to 2026-11-04 |
| `csco_ifndq` | view | 7 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_ifndytd` | view | 7 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_ifntq` | view | 7 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_ifntytd` | view | 7 | `effdate` 1986-12-14 to 2026-11-04 |
| `csco_ikey` | view | 16 | `datadate` 1973-09-30 to 2027-05-31 |
| `csco_ipcd` | view (empty) | 4 | `effdate`, not asked |
| `csco_itxt` | view | 6 | `effdate` 1986-12-14 to 2026-11-04 |
| `cscompany` | view | 35 | `dldte` 1964-01-10 to 2026-10-22 |
| `cssecurity` | view | 16 | `dldtei` 1900-01-01 to 2026-11-04 |
| `dd_group` | view | 5 | - |
| `dd_group_xref` | view | 3 | - |
| `dd_item` | view | 15 | - |
| `dd_package` | view | 4 | - |
| `r_actioncd` | view | 2 | - |
| `sec_idhist` | view | 6 | `efffrom` 1900-01-01 to 2028-12-15 |
| `wrds_cs_names` | view | 43 | `begdate` 1986-12-14 to 2026-11-05 |
| `wrds_csa_pit` | view | 656 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_pit_dc` | view | 512 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_pit_dc_sorted` | view | 512 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_pit_sorted` | view | 656 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csa_restated` | view | 656 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csa_restated_dc` | view | 512 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csa_unrestated` | view | 656 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csa_unrestated_dc` | view | 512 | `datadate` 1968-06-30 to 2027-05-31 |
| `wrds_csq_pit` | view | 672 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csq_pit_dc` | view | 516 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csq_pit_dc_sorted` | view | 516 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csq_pit_sorted` | view | 672 | `pitdate1` 1986-12-14 to 2026-11-04 |
| `wrds_csq_restated` | view | 672 | `datadate` 1973-09-30 to 2027-05-31 |
| `wrds_csq_restated_dc` | view | 516 | `datadate` 1973-09-30 to 2027-05-31 |
| `wrds_csq_unrestated` | view | 672 | `datadate` 1973-09-30 to 2027-05-31 |
| `wrds_csq_unrestated_dc` | view | 516 | `datadate` 1973-09-30 to 2027-05-31 |
| `xfc_actionstartconditiontype` | view | 2 | - |
| `xfc_actionstatetype` | view | 2 | - |
| `xfc_actiontype` | view | 5 | - |
| `xfc_activitytype` | view | 2 | - |
| `xfc_changeflagtype` | view | 3 | - |
| `xfc_cleanuptype` | view | 3 | - |
| `xfc_column` | view | 3 | - |
| `xfc_columntodatabasetype` | view | 4 | - |
| `xfc_columnusetype` | view | 2 | - |
| `xfc_databasetype` | view | 2 | - |
| `xfc_datetimeformattype` | view | 3 | - |
| `xfc_datetimetodatabasetype` | view | 3 | - |
| `xfc_daynotinfeedfrequency` | view | 2 | - |
| `xfc_delimitertype` | view | 4 | - |
| `xfc_emailaccounttype` | view | 2 | - |
| `xfc_errormessage` | view (empty) | 5 | - |
| `xfc_failuretype` | view | 2 | - |
| `xfc_feedfrequencytype` | view | 3 | - |
| `xfc_feedpop` | view | 4 | - |
| `xfc_hosttype` | view | 3 | - |
| `xfc_indextype` | view | 4 | - |
| `xfc_lengthsemantictype` | view | 2 | - |
| `xfc_loaderobjecttype` | view | 2 | - |
| `xfc_loadersetting` | view | 5 | - |
| `xfc_loaderver` | view | 8 | `datereleased`, not asked |
| `xfc_loadjobtype` | view | 2 | - |
| `xfc_loadsubstatetype` | view | 2 | - |
| `xfc_loadsubtype` | view | 3 | - |
| `xfc_notificationtype` | view | 3 | - |
| `xfc_pac` | view | 6 | - |
| `xfc_pacgroup` | view | 4 | - |
| `xfc_pacsource` | view | 7 | - |
| `xfc_pacsourcetohost` | view | 12 | - |
| `xfc_pacsourcetype` | view | 3 | - |
| `xfc_pacver` | view | 13 | - |
| `xfc_pacverfeedpoptopacsrchost` | view | 7 | `expiredate` 2014-03-07 to 2026-09-30 |
| `xfc_pacverfeedpoptotableinst` | view | 6 | - |
| `xfc_pacverfeedpoptozipfile` | view | 4 | - |
| `xfc_pacverfeedpopupgrade` | view | 4 | - |
| `xfc_pacverrelationship` | view | 4 | - |
| `xfc_pacvertofeedpop` | view | 4 | - |
| `xfc_phasetype` | view | 2 | - |
| `xfc_prepostloadsql` | view (empty) | 6 | - |
| `xfc_prepostloadtype` | view | 3 | - |
| `xfc_progresstype` | view | 2 | - |
| `xfc_proxyprotocoltype` | view | 2 | - |
| `xfc_relationshiptype` | view | 3 | - |
| `xfc_resulttype` | view | 3 | - |
| `xfc_table` | view | 3 | - |
| `xfc_tableinst` | view | 4 | - |
| `xfc_tableinstindex` | view | 8 | - |
| `xfc_tableinstindexcolumn` | view | 5 | - |
| `xfc_tableinsttocolumn` | view | 6 | - |
| `xfc_tabletype` | view | 2 | - |
| `xfc_textfile` | view | 11 | - |
| `xfc_textfilecolumnmapping` | view | 6 | - |
| `xfc_textfiletype` | view | 2 | - |
| `xfc_upgradeabstraction` | view | 2 | - |
| `xfc_upgradetable` | view | 4 | - |
| `xfc_upgradetablesql` | view (empty) | 3 | - |
| `xfc_upgradetype` | view | 3 | - |
| `xfc_validationtype` | view | 3 | - |
| `xfc_zipfile` | view | 9 | - |
| `xfc_zipfiletotextfile` | view | 2 | - |
| `xfc_zipfiletype` | view | 2 | - |
| `xfc_zipruntype` | view | 4 | - |
| `xfl_column` | view | 15 | - |
| `xfl_datagroup` | view | 3 | - |
| `xfl_datagroup_table` | view | 2 | - |
| `xfl_db_version` | view | 1 | - |
| `xfl_file_datagroup` | view | 3 | - |
| `xfl_filelayout` | view | 7 | - |
| `xfl_lrm_cstat_fsup0` | view | 2 | - |
| `xfl_lrm_cstat_fsup0_2` | view | 4 | `loaddate` 2013-03-16 to 2013-03-17 |
| `xfl_lrm_cstat_rsup0` | view | 3 | - |
| `xfl_lrm_cstat_tsup0` | view | 4 | `loaddate` 2013-10-07 to 2013-10-07 |
| `xfl_lrm_user_load_plan` | view | 1 | - |
| `xfl_mapping` | view | 4 | - |
| `xfl_package` | view | 9 | - |
| `xfl_package_file` | view | 9 | - |
| `xfl_package_rel` | view | 4 | - |
| `xfl_refer` | view | 5 | - |
| `xfl_sequence` | view | 2 | - |
| `xfl_table` | view | 6 | - |

## contrib

| table | rows | columns | dates |
|---|---|---|---|
| `_states_` | view | 2 | - |
| `arc` | view | 32 | `fiscal_period_end` 2004-12-31 to 2025-03-31 |
| `as_firm_risks` | view | 29 | `filing_date` 2005-01-03 to 2025-01-07 |
| `better_beta` | view | 4 | `yyyymmdd` 1926-07-30 to 2019-12-31 |
| `blocksv` | view | 8 | - |
| `ceo_turnover` | view | 7 | `anndate` 1993-06-19 to 2021-03-12 |
| `char_returns` | view | 7 | `date` 1964-01-31 to 2021-12-31 |
| `cik_types` | view | 4 | - |
| `classified_boards` | view | 6 | `datadate` 1991-06-30 to 2024-09-30 |
| `common_own_firm` | view | 8 | - |
| `common_own_industry` | view | 7 | - |
| `corp_culture` | view | 9 | - |
| `ctff_chars` | view | 410 | `eom` 1951-12-31 to 2023-11-30 |
| `ctff_daily_ret` | view | 3 | `date` 1926-01-02 to 2023-12-29 |
| `ctff_features` | view | 1 | - |
| `dealscan_link_bs` | view | 8 | `ds_start` 1982-06-29 to 2012-07-31 |
| `dealscan_link_comp` | view | 8 | `ds_start` 1900-01-01 to 2019-12-31 |
| `factors` | view | 13 | - |
| `factors_daily` | view | 15 | `date` 1989-07-03 to 2018-02-14 |
| `factors_eq` | view | 13 | - |
| `factors_eq_usd` | view | 13 | - |
| `factors_usd` | view | 13 | - |
| `firm_year_panel` | view | 17 | - |
| `firmyear_level` | view | 23 | - |
| `global_factor` | view | 444 | `date` 1925-12-31 to 2025-12-31 |
| `int_factors` | view | 4 | `date` 1975-01-31 to 2018-12-31 |
| `int_xsec` | view | 12 | `datadate` 1975-01-31 to 2018-05-31 |
| `kpss_patents` | view | 7 | `filing_date` 1834-03-29 to 2019-09-26 |
| `kpss_permco_link` | view | 3 | - |
| `lawsuit_level` | view | 9 | `datefiled` 2006-01-01 to 2021-12-31 |
| `liva` | view | 10 | - |
| `marginal_tax` | view | 4 | - |
| `patent_level` | view | 18 | - |
| `rq_data` | view | 8 | - |
| `shale` | view | 5 | `year_month` 2003-01-01 to 2019-08-01 |

## contrib_ceo_turnover

| table | rows | columns | dates |
|---|---|---|---|
| `ceo_turnover` | 1,438 | 7 | `anndate` 1993-06-19 to 2021-10-21 |

## contrib_char_returns

| table | rows | columns | dates |
|---|---|---|---|
| `char_returns` | 2,578,736 | 7 | `date` 1964-01-31 to 2021-12-31 |

## contrib_corp_fed_litigation

| table | rows | columns | dates |
|---|---|---|---|
| `firmyear_level` | 50,447 | 23 | - |
| `lawsuit_level` | 218,437 | 9 | `datefiled` 2006-01-01 to 2021-12-31 |

## contrib_corporate_culture

| table | rows | columns | dates |
|---|---|---|---|
| `corp_culture` | 102,688 | 9 | - |

## contrib_general

| table | rows | columns | dates |
|---|---|---|---|
| `_states_` | 58 | 2 | - |
| `arc` | 390,956 | 32 | `fiscal_period_end` 2004-12-31 to 2025-03-31 |
| `as_firm_risks` | 131,920 | 29 | `filing_date` 2005-01-03 to 2025-01-07 |
| `better_beta` | 4,465,811 | 4 | `yyyymmdd` 1926-07-30 to 2019-12-31 |
| `blocksv` | 608,362 | 8 | - |
| `ceo_turnover` | 1,397 | 7 | `anndate` 1993-06-19 to 2021-03-12 |
| `cik_types` | 50,785 | 4 | - |
| `classified_boards` | 149,695 | 6 | `datadate` 1991-06-30 to 2024-09-30 |
| `common_own_firm` | 1,139,330,176 | 8 | - |
| `common_own_industry` | 6,513 | 7 | - |
| `dealscan_link_bs` | 683 | 8 | `ds_start` 1982-06-29 to 2012-07-31 |
| `dealscan_link_comp` | 1,559 | 8 | `ds_start` 1900-01-01 to 2019-12-31 |
| `factors` | 4,015 | 13 | - |
| `factors_daily` | 117,031 | 15 | `date` 1989-07-03 to 2018-02-14 |
| `factors_eq` | 6,973 | 13 | - |
| `factors_eq_usd` | 7,292 | 13 | - |
| `factors_usd` | 4,653 | 13 | - |
| `liva` | 531,795 | 10 | - |
| `marginal_tax` | 198,785 | 4 | - |
| `shale` | 20,617 | 5 | `year_month` 2003-01-01 to 2019-08-01 |

## contrib_global_factor

| table | rows | columns | dates |
|---|---|---|---|
| `ctff_chars` | 1,369,324 | 410 | `eom` 1951-12-31 to 2023-11-30 |
| `ctff_daily_ret` | 103,382,880 | 3 | `date`, not asked (too big) |
| `ctff_features` | 402 | 1 | - |
| `global_factor` | 16,008,333 | 444 | `date`, not asked (too big) |

## contrib_intangible_value

| table | rows | columns | dates |
|---|---|---|---|
| `int_factors` | 528 | 4 | `date` 1975-01-31 to 2018-12-31 |
| `int_xsec` | 189,198 | 12 | `datadate` 1975-01-31 to 2018-05-31 |

## contrib_kpss

| table | rows | columns | dates |
|---|---|---|---|
| `kpss_patents` | 2,950,305 | 7 | `filing_date` 1834-03-29 to 2019-09-26 |
| `kpss_permco_link` | 2,950,305 | 3 | - |

## contrib_liva

| table | rows | columns | dates |
|---|---|---|---|
| `liva` | 531,795 | 10 | - |

## contrib_patent_firm_link

| table | rows | columns | dates |
|---|---|---|---|
| `firm_year_panel` | 593,488 | 17 | - |
| `patent_level` | 8,531,932 | 18 | - |

## contrib_shale

| table | rows | columns | dates |
|---|---|---|---|
| `_states_` | view | 2 | - |
| `shale` | 20,617 | 5 | `year_month` 2003-01-01 to 2019-08-01 |

## crsp

| table | rows | columns | dates |
|---|---|---|---|
| `cap` | view | 19 | `tradetstmp` 2011-04-01 to 2026-09-30 |
| `core` | view | 13 | `tradetstmp` 2023-12-04 to 2026-09-30 |
| `dse` | view | 50 | `date` 1925-12-31 to 2024-12-31 |
| `dseall` | view | 48 | `date` 1925-12-31 to 2024-12-31 |
| `dsedelist` | view | 19 | `dlstdt` 1926-02-24 to 2024-12-31 |
| `dsedist` | view | 17 | `dclrdt` 1961-10-03 to 2024-12-31 |
| `dseexchdates` | view | 25 | `namedt` 1925-12-31 to 2024-12-31 |
| `dsenames` | view | 21 | `namedt` 1925-12-31 to 2024-12-31 |
| `dsenasdin` | view | 13 | `trtsdt` 1982-04-01 to 2024-12-31 |
| `dseshares` | view | 11 | `shrsdt` 1925-12-31 to 2024-12-31 |
| `dsf` | view | 20 | `date` 1925-12-31 to 2024-12-31 |
| `dsf_v2` | view | 50 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `dsfhdr` | view | 44 | `begdat` 1925-12-31 to 2024-12-31 |
| `dsi` | view | 11 | `date` 1925-12-31 to 2024-12-31 |
| `eod_cap` | view | 18 | `date` 2011-03-31 to 2026-09-30 |
| `eod_core` | view | 12 | `date` 2023-12-01 to 2026-09-30 |
| `eod_esg` | view | 14 | `date` 2021-09-03 to 2026-06-30 |
| `eod_sector` | view | 24 | `date` 2012-09-20 to 2026-09-30 |
| `eod_vg` | view | 22 | `date` 2012-09-07 to 2026-09-30 |
| `esg` | view | 15 | `tradetstmp` 2021-09-07 to 2026-06-30 |
| `inddlyseriesdata` | view | 15 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `index_descriptions` | view | 8 | `nasdaq_gids_postdt` 2011-01-18 to 2021-09-07 |
| `indfamilyinfohdr` | view | 23 | `indfambegdt` 1925-12-31 to 1972-12-14 |
| `indmthseriesdata` | view | 15 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `indseriesinfohdr` | view | 12 | `indbegdt` 1925-12-31 to 1972-12-14 |
| `metacalendarperiod` | view | 14 | `calperiodstartdt` 1925-01-01 to 2028-12-29 |
| `metacolumncoverage` | view | 14 | - |
| `metacolumninfo` | view | 14 | - |
| `metaexchangecalendar` | view | 7 | `caldt` 1925-12-31 to 2025-12-31 |
| `metafileinfo` | view | 19 | - |
| `metaflagcoverage` | view | 18 | - |
| `metaflaginfo` | view | 7 | - |
| `metaflagtype` | view | 6 | - |
| `metaiteminfo` | view | 13 | - |
| `metasiztociz` | view | 14 | - |
| `mse` | view | 50 | `date` 1925-12-31 to 2024-12-31 |
| `mseall` | view | 50 | `date` 1925-12-31 to 2024-12-31 |
| `msedelist` | view | 19 | `dlstdt` 1926-02-24 to 2024-12-31 |
| `msedist` | view | 17 | `dclrdt` 1961-10-03 to 2024-12-31 |
| `mseexchdates` | view | 25 | `namedt` 1925-12-31 to 2024-12-31 |
| `msenames` | view | 21 | `namedt` 1925-12-31 to 2024-12-31 |
| `msenasdin` | view | 13 | `trtsdt` 1982-04-01 to 2024-12-31 |
| `mseshares` | view | 11 | `shrsdt` 1925-12-31 to 2024-12-31 |
| `msf` | view | 21 | `date` 1925-12-31 to 2024-12-31 |
| `msf_v2` | view | 45 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `msfhdr` | view | 46 | `begdat` 1925-12-31 to 2024-12-31 |
| `msi` | view | 11 | `date` 1925-12-31 to 2024-12-31 |
| `saz_agg_ann` | view | 31 | `acaldt` 1925-12-31 to 2024-12-31 |
| `saz_agg_ann_legacy` | view | 31 | `acaldt` 1925-12-31 to 2023-12-29 |
| `saz_agg_mth` | view | 31 | `mcaldt` 1925-12-31 to 2024-12-31 |
| `saz_agg_mth_legacy` | view | 31 | `mcaldt` 1925-12-31 to 2023-12-29 |
| `saz_agg_qtr` | view | 31 | `qcaldt` 1925-12-31 to 2024-12-31 |
| `saz_agg_qtr_legacy` | view | 31 | `qcaldt` 1925-12-31 to 2023-12-29 |
| `saz_del` | view | 11 | `dlstdt` 1926-02-24 to 2024-12-31 |
| `saz_del_legacy` | view | 11 | `dlstdt` 1926-02-24 to 2023-12-29 |
| `saz_dind` | view | 12 | `caldt` 1925-12-31 to 2024-12-31 |
| `saz_dind_legacy` | view | 12 | `caldt` 1925-12-31 to 2023-12-29 |
| `saz_dis` | view | 11 | `dclrdt` 1961-10-03 to 2024-12-31 |
| `saz_dis_legacy` | view | 11 | `dclrdt` 1961-10-03 to 2023-12-28 |
| `saz_dp_dly` | view | 7 | `caldt` 1925-12-31 to 2024-12-31 |
| `saz_dp_dly_legacy` | view | 7 | `caldt` 1925-12-31 to 2023-12-29 |
| `saz_ds_dly` | view | 8 | `caldt` 1925-12-31 to 2024-12-31 |
| `saz_ds_dly_legacy` | view | 8 | `caldt` 1925-12-31 to 2023-12-29 |
| `saz_hdr` | view | 19 | `begdt` 1925-12-31 to 2024-12-31 |
| `saz_hdr_legacy` | view | 19 | `begdt` 1925-12-31 to 2023-12-29 |
| `saz_indhdr` | view | 15 | `indbegdt` 1925-12-31 to 1972-12-14 |
| `saz_indhdr_legacy` | view | 15 | `indbegdt` 1925-12-31 to 1972-12-14 |
| `saz_mdel` | view | 11 | `mdlstdt` 1926-02-24 to 2024-12-31 |
| `saz_mdel_legacy` | view | 11 | `mdlstdt` 1926-02-24 to 2023-12-29 |
| `saz_mind` | view | 12 | `mcaldt` 1925-12-31 to 2024-12-31 |
| `saz_mind_legacy` | view | 12 | `mcaldt` 1925-12-31 to 2023-12-29 |
| `saz_mth` | view | 14 | `mcaldt` 1925-12-31 to 2024-12-31 |
| `saz_mth_legacy` | view | 14 | `mcaldt` 1925-12-31 to 2023-12-29 |
| `saz_nam` | view | 16 | `namedt` 1925-12-31 to 2024-12-31 |
| `saz_nam_legacy` | view | 16 | `namedt` 1925-12-31 to 2023-12-29 |
| `saz_ndi` | view | 7 | `trtsdt` 1982-04-01 to 2024-12-31 |
| `saz_ndi_legacy` | view | 7 | `trtsdt` 1982-04-01 to 2023-12-29 |
| `saz_shr` | view | 5 | `shrsdt` 1925-12-31 to 2024-12-31 |
| `saz_shr_legacy` | view | 5 | `shrsdt` 1925-12-31 to 2023-12-29 |
| `sector` | view | 25 | `tradetstmp` 2012-09-21 to 2026-09-30 |
| `stkannsecuritydata` | view | 37 | `anncaldt` 1925-12-31 to 2025-12-31 |
| `stkdelists` | view | 19 | `delistingdt` 1926-02-24 to 2025-12-30 |
| `stkdistributions` | view | 19 | `disexdt` 1926-01-04 to 2025-12-31 |
| `stkdlycumulativeadjfactor` | view | 5 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `stkdlysecuritydata` | view | 32 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `stkdlysecurityprimarydata` | view | 12 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `stkissuerinfohdr` | view | 18 | `issinfostartdt` 1925-12-31 to 2025-12-31 |
| `stkissuerinfohist` | view | 18 | `issinfostartdt` 1925-12-31 to 2025-12-31 |
| `stkmthcumulativeadjfactor` | view | 5 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `stkmthfloatshares` | view | 4 | - |
| `stkmthsecuritydata` | view | 37 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `stkqtrsecuritydata` | view | 37 | `qtrcaldt` 1925-12-31 to 2025-12-31 |
| `stksecurityinfohdr` | view | 36 | `secinfostartdt` 1925-12-31 to 2025-12-31 |
| `stksecurityinfohist` | view | 36 | `secinfostartdt` 1925-12-31 to 2025-12-31 |
| `stkshares` | view | 7 | `shrstartdt` 1925-12-31 to 2025-12-31 |
| `stock_qvards` | view (empty) | 51 | `date`, not asked |
| `stocknames` | view | 16 | `namedt` 1925-12-31 to 2024-12-31 |
| `stocknames_v2` | view | 22 | `namedt` 1925-12-31 to 2025-12-31 |
| `vg` | view | 23 | `tradetstmp` 2012-09-10 to 2026-09-30 |
| `wrds_dailyindexret_query` | view | 15 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `wrds_dsfv2_query` | view | 98 | `secinfostartdt` 1925-12-31 to 2025-12-31 |
| `wrds_monthlyindexret_query` | view | 15 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `wrds_msfv2_query` | view | 91 | `secinfostartdt` 1925-12-31 to 2025-12-31 |
| `wrds_names_query` | view | 24 | `secinfostartdt` 1925-12-31 to 2025-12-31 |

## crsp_a_stock

| table | rows | columns | dates |
|---|---|---|---|
| `dse` | 12,997,940 | 50 | `date`, not asked (too big) |
| `dseall` | 12,450,527 | 48 | `date`, not asked (too big) |
| `dsedelist` | 38,872 | 19 | `dlstdt` 1926-02-24 to 2024-12-31 |
| `dsedist` | 1,064,794 | 17 | `dclrdt` 1961-10-03 to 2024-12-31 |
| `dseexchdates` | 117,859 | 25 | `namedt` 1925-12-31 to 2024-12-31 |
| `dsenames` | 117,859 | 21 | `namedt` 1925-12-31 to 2024-12-31 |
| `dsenasdin` | 8,861,556 | 13 | `trtsdt`, not asked (too big) |
| `dseshares` | 2,913,355 | 11 | `shrsdt` 1925-12-31 to 2024-12-31 |
| `dsf` | 107,682,104 | 20 | `date`, not asked (too big) |
| `dsf_v2` | 110,257,376 | 50 | `dlycaldt`, not asked (too big) |
| `dsfhdr` | 38,872 | 44 | `begdat` 1925-12-31 to 2024-12-31 |
| `dsi` | 26,051 | 11 | `date` 1925-12-31 to 2024-12-31 |
| `dsiy` | 24,039 | 11 | `caldt` 1925-12-31 to 2016-12-30 |
| `inddlyseriesdata` | 81,957 | 15 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `indfamilyinfohdr` | 3 | 23 | `indfambegdt` 1925-12-31 to 1972-12-14 |
| `indmthseriesdata` | 4,240 | 15 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `indseriesinfohdr` | 4 | 12 | `indbegdt` 1925-12-31 to 1972-12-14 |
| `metacalendarperiod` | 28,808 | 14 | `calperiodstartdt` 1925-01-01 to 2028-12-29 |
| `metacolumncoverage` | 124 | 14 | - |
| `metacolumninfo` | 577 | 14 | - |
| `metaexchangecalendar` | 36,526 | 7 | `caldt` 1925-12-31 to 2025-12-31 |
| `metafileinfo` | 34 | 19 | - |
| `metaflagcoverage` | 1,046 | 18 | - |
| `metaflaginfo` | 774 | 7 | - |
| `metaflagtype` | 62 | 6 | - |
| `metaiteminfo` | 392 | 13 | - |
| `metasiztociz` | 473 | 14 | - |
| `mse` | 12,995,885 | 50 | `date`, not asked (too big) |
| `mseall` | 3,744,882 | 50 | `date` 1925-12-31 to 2024-12-31 |
| `msedelist` | 38,843 | 19 | `dlstdt` 1926-02-24 to 2024-12-31 |
| `msedist` | 1,064,791 | 17 | `dclrdt` 1961-10-03 to 2024-12-31 |
| `mseexchdates` | 117,859 | 25 | `namedt` 1925-12-31 to 2024-12-31 |
| `msenames` | 117,830 | 21 | `namedt` 1925-12-31 to 2024-12-31 |
| `msenasdin` | 8,861,489 | 13 | `trtsdt`, not asked (too big) |
| `mseshares` | 2,913,327 | 11 | `shrsdt` 1925-12-31 to 2024-12-31 |
| `msf` | 5,153,763 | 21 | `date`, not asked (too big) |
| `msf_v2` | 5,240,430 | 45 | `mthcaldt`, not asked (too big) |
| `msfhdr` | 38,843 | 46 | `begdat` 1925-12-31 to 2024-12-31 |
| `msi` | 1,189 | 11 | `date` 1925-12-31 to 2024-12-31 |
| `msiy` | 1,093 | 11 | `caldt` 1925-12-31 to 2016-12-30 |
| `saz_agg_ann` | 459,406 | 31 | `acaldt` 1925-12-31 to 2024-12-31 |
| `saz_agg_ann_legacy` | 448,890 | 31 | `acaldt` 1925-12-31 to 2023-12-29 |
| `saz_agg_mth` | 5,117,080 | 31 | `mcaldt`, not asked (too big) |
| `saz_agg_mth_legacy` | 5,001,778 | 31 | `mcaldt`, not asked (too big) |
| `saz_agg_qtr` | 1,729,036 | 31 | `qcaldt` 1925-12-31 to 2024-12-31 |
| `saz_agg_qtr_legacy` | 1,689,951 | 31 | `qcaldt` 1925-12-31 to 2023-12-29 |
| `saz_del` | 38,872 | 11 | `dlstdt` 1926-02-24 to 2024-12-31 |
| `saz_del_legacy` | 37,776 | 11 | `dlstdt` 1926-02-24 to 2023-12-29 |
| `saz_dind` | 80,957 | 12 | `caldt` 1925-12-31 to 2024-12-31 |
| `saz_dind_legacy` | 79,949 | 12 | `caldt` 1925-12-31 to 2023-12-29 |
| `saz_dis` | 1,064,776 | 11 | `dclrdt` 1961-10-03 to 2024-12-31 |
| `saz_dis_legacy` | 1,033,746 | 11 | `dclrdt` 1961-10-03 to 2023-12-28 |
| `saz_dp_dly` | 107,631,792 | 7 | `caldt`, not asked (too big) |
| `saz_dp_dly_legacy` | 105,279,520 | 7 | `caldt`, not asked (too big) |
| `saz_ds_dly` | 107,682,888 | 8 | `caldt`, not asked (too big) |
| `saz_ds_dly_legacy` | 105,232,656 | 8 | `caldt`, not asked (too big) |
| `saz_hdr` | 38,872 | 19 | `begdt` 1925-12-31 to 2024-12-31 |
| `saz_hdr_legacy` | 37,776 | 19 | `begdt` 1925-12-31 to 2023-12-29 |
| `saz_indhdr` | 4 | 15 | `indbegdt` 1925-12-31 to 1972-12-14 |
| `saz_indhdr_legacy` | 4 | 15 | `indbegdt` 1925-12-31 to 1972-12-14 |
| `saz_mdel` | 38,843 | 11 | `mdlstdt` 1926-02-24 to 2024-12-31 |
| `saz_mdel_legacy` | 37,747 | 11 | `mdlstdt` 1926-02-24 to 2023-12-29 |
| `saz_mind` | 4,192 | 12 | `mcaldt` 1925-12-31 to 2024-12-31 |
| `saz_mind_legacy` | 4,144 | 12 | `mcaldt` 1925-12-31 to 2023-12-29 |
| `saz_mth` | 5,153,792 | 14 | `mcaldt`, not asked (too big) |
| `saz_mth_legacy` | 5,037,353 | 14 | `mcaldt`, not asked (too big) |
| `saz_nam` | 113,112 | 16 | `namedt` 1925-12-31 to 2024-12-31 |
| `saz_nam_legacy` | 113,885 | 16 | `namedt` 1925-12-31 to 2023-12-29 |
| `saz_ndi` | 8,799,555 | 7 | `trtsdt`, not asked (too big) |
| `saz_ndi_legacy` | 8,617,950 | 7 | `trtsdt`, not asked (too big) |
| `saz_shr` | 2,938,356 | 5 | `shrsdt` 1925-12-31 to 2024-12-31 |
| `saz_shr_legacy` | 2,785,564 | 5 | `shrsdt` 1925-12-31 to 2023-12-29 |
| `stkannsecuritydata` | 470,840 | 37 | `anncaldt` 1925-12-31 to 2025-12-31 |
| `stkdelists` | 29,833 | 19 | `delistingdt` 1926-02-24 to 2025-12-30 |
| `stkdistributions` | 1,101,681 | 19 | `disexdt` 1926-01-04 to 2025-12-31 |
| `stkdlycumulativeadjfactor` | 110,227,992 | 5 | `dlycaldt`, not asked (too big) |
| `stkdlysecuritydata` | 110,162,368 | 32 | `dlycaldt`, not asked (too big) |
| `stkdlysecurityprimarydata` | 110,262,024 | 12 | `dlycaldt`, not asked (too big) |
| `stkissuerinfohdr` | 33,163 | 18 | `issinfostartdt` 1925-12-31 to 2025-12-31 |
| `stkissuerinfohist` | 139,528 | 18 | `issinfostartdt` 1925-12-31 to 2025-12-31 |
| `stkmthcumulativeadjfactor` | 5,214,166 | 5 | `mthcaldt`, not asked (too big) |
| `stkmthfloatshares` | 1,477,774 | 4 | - |
| `stkmthsecuritydata` | 5,240,606 | 37 | `mthcaldt`, not asked (too big) |
| `stkqtrsecuritydata` | 1,771,003 | 37 | `qtrcaldt` 1925-12-31 to 2025-12-31 |
| `stksecurityinfohdr` | 40,518 | 36 | `secinfostartdt` 1925-12-31 to 2025-12-31 |
| `stksecurityinfohist` | 191,048 | 36 | `secinfostartdt` 1925-12-31 to 2025-12-31 |
| `stkshares` | 3,087,489 | 7 | `shrstartdt` 1925-12-31 to 2025-12-31 |
| `stock_qvards` | view (empty) | 51 | `date`, not asked |
| `stocknames` | 83,280 | 16 | `namedt` 1925-12-31 to 2024-12-31 |
| `stocknames_v2` | 86,060 | 22 | `namedt` 1925-12-31 to 2025-12-31 |
| `wrds_dailyindexret_query` | 26,301 | 15 | `dlycaldt` 1925-12-31 to 2025-12-31 |
| `wrds_dsfv2_query` | 110,261,760 | 98 | `secinfostartdt`, not asked (too big) |
| `wrds_monthlyindexret_query` | 1,201 | 15 | `mthcaldt` 1925-12-31 to 2025-12-31 |
| `wrds_msfv2_query` | 5,306,839 | 91 | `secinfostartdt`, not asked (too big) |
| `wrds_names_query` | 191,048 | 24 | `secinfostartdt` 1925-12-31 to 2025-12-31 |

## crsp_q_indexhist

| table | rows | columns | dates |
|---|---|---|---|
| `cap` | 90,837,296 | 19 | `tradetstmp`, not asked (too big) |
| `core` | 16,503,108 | 13 | `tradetstmp`, not asked (too big) |
| `eod_cap` | 3,898 | 18 | `date` 2011-03-31 to 2026-09-30 |
| `eod_core` | 709 | 12 | `date` 2023-12-01 to 2026-09-30 |
| `eod_esg` | 1,209 | 14 | `date` 2021-09-03 to 2026-06-30 |
| `eod_sector` | 3,526 | 24 | `date` 2012-09-20 to 2026-09-30 |
| `eod_vg` | 3,535 | 22 | `date` 2012-09-07 to 2026-09-30 |
| `esg` | 28,160,408 | 15 | `tradetstmp`, not asked (too big) |
| `index_descriptions` | 73 | 8 | `nasdaq_gids_postdt` 2011-01-18 to 2021-09-07 |
| `sector` | 82,153,728 | 25 | `tradetstmp`, not asked (too big) |
| `vg` | 82,364,336 | 23 | `tradetstmp`, not asked (too big) |

## crspsamp

| table | rows | columns | dates |
|---|---|---|---|
| `ccm_qvards` | view (empty) | 10 | - |
| `ccmlinktable_trial` | view | 9 | `linkdt` 1949-10-01 to 2007-08-25 |
| `ccmnames_trial` | view | 40 | `ipodate` 1987-01-01 to 1998-12-09 |
| `ccmxpf_lnkhist` | view | 8 | `linkdt` 1949-10-01 to 2014-03-31 |
| `comphead` | view | 38 | `ipodate` 1986-03-13 to 1998-12-09 |
| `contact_info` | view | 11 | `chgdt` 2004-06-30 to 2006-12-31 |
| `crspdsf` | view | 56 | `date` 1962-07-02 to 2004-12-31 |
| `crspmsf` | view | 55 | `date` 1925-12-31 to 2004-12-31 |
| `daily_nav_ret` | view | 4 | `caldt` 2004-01-02 to 2006-12-29 |
| `dividends` | view | 6 | `caldt` 2004-01-02 to 2006-12-31 |
| `dsenames_trial` | view | 21 | `namedt` 1925-12-31 to 2011-06-13 |
| `dsf_v2` | view | 50 | `dlycaldt` 1925-12-31 to 2021-12-31 |
| `dsftrial` | view | 62 | `date` 1926-01-02 to 2009-12-31 |
| `front_load` | view | 6 | `begdt` 2004-01-01 to 2006-12-29 |
| `front_load_grp` | view | 4 | `begdt` 2004-01-01 to 2006-12-29 |
| `fund_fees` | view | 9 | `begdt` 2004-01-31 to 2006-12-31 |
| `fund_hdr_hist` | view | 21 | `chgdt` 2004-01-31 to 2006-12-31 |
| `fund_names` | view | 26 | `chgdt` 2004-01-01 to 2006-12-31 |
| `fund_style` | view | 14 | `begdt` 2004-06-30 to 2006-12-31 |
| `fund_summary` | view | 33 | `caldt` 2004-03-31 to 2006-12-29 |
| `fund_summary2` | view | 73 | `caldt` 2004-03-31 to 2006-12-29 |
| `holdings` | view | 15 | `report_dt` 2004-01-31 to 2006-12-31 |
| `inddlyseriesdata` | view | 15 | `dlycaldt` 2021-01-04 to 2021-12-31 |
| `indfamilyinfohdr` | view | 23 | `indfambegdt` 1925-12-31 to 2011-03-31 |
| `indmthseriesdata` | view | 15 | `mthcaldt` 2021-01-29 to 2021-12-31 |
| `indseriesinfohdr` | view | 12 | `indbegdt` 1925-12-31 to 2011-03-31 |
| `metacalendarperiod` | view | 14 | `calperiodstartdt` 1925-01-01 to 2028-09-29 |
| `metacolumncoverage` | view | 14 | - |
| `metacolumninfo` | view | 14 | - |
| `metaexchangecalendar` | view | 7 | `caldt` 1925-12-31 to 2025-09-30 |
| `metafileinfo` | view | 19 | - |
| `metaflagcoverage` | view | 18 | - |
| `metaflaginfo` | view | 7 | - |
| `metaflagtype` | view | 6 | - |
| `metaiteminfo` | view | 13 | - |
| `metasiztociz` | view | 14 | - |
| `monthly_tna_ret_nav` | view | 5 | `caldt` 2004-01-30 to 2006-12-29 |
| `msf_v2` | view | 45 | `mthcaldt` 1925-12-31 to 2021-12-31 |
| `msftrial` | view | 64 | `date` 1925-12-31 to 2009-12-31 |
| `portnomap` | view | 25 | `begdt` 2004-01-30 to 2006-12-29 |
| `rear_load` | view | 8 | `begdt` 2004-01-01 to 2006-12-31 |
| `rear_load_grp` | view | 4 | `begdt` 2004-01-01 to 2006-12-31 |
| `stkannsecuritydata` | view | 37 | `anncaldt` 1925-12-31 to 2021-12-31 |
| `stkdelists` | view | 19 | `delistingdt` 1984-10-18 to 2015-07-24 |
| `stkdistributions` | view | 18 | `disexdt` 1926-01-15 to 2021-12-09 |
| `stkdlycumulativeadjfactor` | view | 5 | `dlycaldt` 1925-12-31 to 2025-09-30 |
| `stkdlysecuritydata` | view | 32 | `dlycaldt` 1925-12-31 to 2021-12-31 |
| `stkdlysecurityprimarydata` | view | 12 | `dlycaldt` 1925-12-31 to 2021-12-31 |
| `stkissuerinfohdr` | view | 17 | `issinfostartdt` 1971-03-03 to 2021-12-03 |
| `stkissuerinfohist` | view | 17 | `issinfostartdt` 1925-12-31 to 2021-12-03 |
| `stkmthcumulativeadjfactor` | view | 5 | `mthcaldt` 1925-12-31 to 2025-09-30 |
| `stkmthfloatshares` | view (empty) | 4 | - |
| `stkmthsecuritydata` | view | 37 | `mthcaldt` 1925-12-31 to 2021-12-31 |
| `stkqtrsecuritydata` | view | 37 | `qtrcaldt` 1925-12-31 to 2021-12-31 |
| `stksecurityinfohdr` | view | 35 | `secinfostartdt` 1971-03-03 to 2021-12-03 |
| `stksecurityinfohist` | view | 35 | `secinfostartdt` 1925-12-31 to 2021-12-03 |
| `stkshares` | view | 7 | `shrstartdt` 1925-12-31 to 2021-12-31 |
| `stocknames_v2` | view | 22 | `namedt` 1925-12-31 to 2021-12-03 |
| `wrds_dailyindexret_query` | view (empty) | 15 | `dlycaldt`, not asked |
| `wrds_dsfv2_query` | view | 96 | `secinfostartdt` 1925-12-31 to 2021-12-03 |
| `wrds_monthlyindexret_query` | view (empty) | 15 | `mthcaldt`, not asked |
| `wrds_msfv2_query` | view | 89 | `secinfostartdt` 1925-12-31 to 2021-12-03 |
| `wrds_names_query` | view | 24 | `secinfostartdt` 1925-12-31 to 2021-12-03 |

## crspsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `ccm_qvards` | view (empty) | 10 | - |
| `ccmlinktable_trial` | 131 | 9 | `linkdt` 1949-10-01 to 2007-08-25 |
| `ccmnames_trial` | 36 | 40 | `ipodate` 1987-01-01 to 1998-12-09 |
| `ccmxpf_lnkhist` | 86 | 8 | `linkdt` 1949-10-01 to 2014-03-31 |
| `comphead` | 25 | 38 | `ipodate` 1986-03-13 to 1998-12-09 |
| `crspdsf` | 128,530 | 56 | `date` 1962-07-02 to 2004-12-31 |
| `crspmsf` | 9,511 | 55 | `date` 1925-12-31 to 2004-12-31 |
| `dsenames_trial` | 117 | 21 | `namedt` 1925-12-31 to 2011-06-13 |
| `dsf_v2` | 240,074 | 50 | `dlycaldt` 1925-12-31 to 2021-12-31 |
| `dsftrial` | 191,110 | 62 | `date` 1926-01-02 to 2009-12-31 |
| `inddlyseriesdata` | 3,772 | 15 | `dlycaldt` 2021-01-04 to 2021-12-31 |
| `indfamilyinfohdr` | 5 | 23 | `indfambegdt` 1925-12-31 to 2011-03-31 |
| `indmthseriesdata` | 168 | 15 | `mthcaldt` 2021-01-29 to 2021-12-31 |
| `indseriesinfohdr` | 15 | 12 | `indbegdt` 1925-12-31 to 2011-03-31 |
| `metacalendarperiod` | 28,741 | 14 | `calperiodstartdt` 1925-01-01 to 2028-09-29 |
| `metacolumncoverage` | 124 | 14 | - |
| `metacolumninfo` | 577 | 14 | - |
| `metaexchangecalendar` | 36,434 | 7 | `caldt` 1925-12-31 to 2025-09-30 |
| `metafileinfo` | 34 | 19 | - |
| `metaflagcoverage` | 1,051 | 18 | - |
| `metaflaginfo` | 774 | 7 | - |
| `metaflagtype` | 62 | 6 | - |
| `metaiteminfo` | 392 | 13 | - |
| `metasiztociz` | 473 | 14 | - |
| `msf_v2` | 11,091 | 45 | `mthcaldt` 1925-12-31 to 2021-12-31 |
| `msftrial` | 9,009 | 64 | `date` 1925-12-31 to 2009-12-31 |
| `stkannsecuritydata` | 946 | 37 | `anncaldt` 1925-12-31 to 2021-12-31 |
| `stkdelists` | 19 | 19 | `delistingdt` 1984-10-18 to 2015-07-24 |
| `stkdistributions` | 3,533 | 18 | `disexdt` 1926-01-15 to 2021-12-09 |
| `stkdlycumulativeadjfactor` | 245,623 | 5 | `dlycaldt` 1925-12-31 to 2025-09-30 |
| `stkdlysecuritydata` | 240,074 | 32 | `dlycaldt` 1925-12-31 to 2021-12-31 |
| `stkdlysecurityprimarydata` | 240,074 | 12 | `dlycaldt` 1925-12-31 to 2021-12-31 |
| `stkissuerinfohdr` | 23 | 17 | `issinfostartdt` 1971-03-03 to 2021-12-03 |
| `stkissuerinfohist` | 149 | 17 | `issinfostartdt` 1925-12-31 to 2021-12-03 |
| `stkmthcumulativeadjfactor` | 11,341 | 5 | `mthcaldt` 1925-12-31 to 2025-09-30 |
| `stkmthfloatshares` | view (empty) | 4 | - |
| `stkmthsecuritydata` | 11,091 | 37 | `mthcaldt` 1925-12-31 to 2021-12-31 |
| `stkqtrsecuritydata` | 3,713 | 37 | `qtrcaldt` 1925-12-31 to 2021-12-31 |
| `stksecurityinfohdr` | 26 | 35 | `secinfostartdt` 1971-03-03 to 2021-12-03 |
| `stksecurityinfohist` | 167 | 35 | `secinfostartdt` 1925-12-31 to 2021-12-03 |
| `stkshares` | 5,130 | 7 | `shrstartdt` 1925-12-31 to 2021-12-31 |
| `stocknames_v2` | 98 | 22 | `namedt` 1925-12-31 to 2021-12-03 |
| `wrds_dailyindexret_query` | view (empty) | 15 | `dlycaldt`, not asked |
| `wrds_dsfv2_query` | 240,242 | 96 | `secinfostartdt` 1925-12-31 to 2021-12-03 |
| `wrds_monthlyindexret_query` | view (empty) | 15 | `mthcaldt`, not asked |
| `wrds_msfv2_query` | 11,312 | 89 | `secinfostartdt` 1925-12-31 to 2021-12-03 |
| `wrds_names_query` | 167 | 24 | `secinfostartdt` 1925-12-31 to 2021-12-03 |

## crspsamp_mf

| table | rows | columns | dates |
|---|---|---|---|
| `contact_info` | 32,034 | 11 | `chgdt` 2004-06-30 to 2006-12-31 |
| `daily_nav_ret` | 15,752,053 | 4 | `caldt`, not asked (too big) |
| `dividends` | 359,582 | 6 | `caldt` 2004-01-02 to 2006-12-31 |
| `front_load` | 12,312 | 6 | `begdt` 2004-01-01 to 2006-12-29 |
| `front_load_grp` | 2,760 | 4 | `begdt` 2004-01-01 to 2006-12-29 |
| `fund_fees` | 55,854 | 9 | `begdt` 2004-01-31 to 2006-12-31 |
| `fund_hdr_hist` | 43,005 | 21 | `chgdt` 2004-01-31 to 2006-12-31 |
| `fund_names` | 53,399 | 26 | `chgdt` 2004-01-01 to 2006-12-31 |
| `fund_style` | 11,790 | 14 | `begdt` 2004-06-30 to 2006-12-31 |
| `fund_summary` | 242,443 | 33 | `caldt` 2004-03-31 to 2006-12-29 |
| `fund_summary2` | 242,443 | 73 | `caldt` 2004-03-31 to 2006-12-29 |
| `holdings` | 4,147,187 | 15 | `report_dt` 2004-01-31 to 2006-12-31 |
| `monthly_tna_ret_nav` | 758,228 | 5 | `caldt` 2004-01-30 to 2006-12-29 |
| `portnomap` | 3,330 | 25 | `begdt` 2004-01-30 to 2006-12-29 |
| `rear_load` | 28,078 | 8 | `begdt` 2004-01-01 to 2006-12-31 |
| `rear_load_grp` | 8,703 | 4 | `begdt` 2004-01-01 to 2006-12-31 |

## csmsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `combas` | 1,553 | 129 | `accper` 1990-12-31 to 2018-09-30 |
| `csmar_t_co` | 10 | 32 | `estbdt` 1984-05-30 to 1990-09-01 |
| `csmar_t_dalyr` | 57,443 | 19 | `trddt` 1991-01-04 to 2018-12-28 |
| `csmar_t_mnth` | 2,921 | 16 | `capchgdt` 1990-12-10 to 2019-01-08 |
| `fund_maininfo` | 6 | 37 | `inceptiondate` 2001-12-18 to 2013-03-22 |
| `wrds_ipo_basics` | 10 | 159 | `estbdt` 1983-07-01 to 1989-10-11 |
| `wrds_stk_ma_trading` | 754 | 22 | `firstdeclaredate` 1997-04-28 to 2018-12-29 |

## djones

| table | rows | columns | dates |
|---|---|---|---|
| `djdaily` | view | 9 | `date` 1896-05-26 to 2008-06-19 |
| `djmonthly` | view | 13 | `date` 1896-05-26 to 2008-06-19 |

## djones_all

| table | rows | columns | dates |
|---|---|---|---|
| `djdaily` | 28,073 | 9 | `date` 1896-05-26 to 2008-06-19 |
| `djmonthly` | 2,429 | 13 | `date` 1896-05-26 to 2008-06-19 |

## dmef

| table | rows | columns | dates |
|---|---|---|---|
| `setfour` | view | 98 | `datead6` 1911-06-01 to 1992-11-30 |
| `setone` | view | 82 | - |
| `setthree` | view | 282 | - |
| `settwo` | view | 170 | - |

## dmef_all

| table | rows | columns | dates |
|---|---|---|---|
| `setfour` | 101,532 | 98 | `datead6` 1911-06-01 to 1992-11-30 |
| `setone` | 99,200 | 82 | - |
| `setthree` | 106,284 | 282 | - |
| `settwo` | 96,551 | 170 | - |

## doe

| table | rows | columns | dates |
|---|---|---|---|
| `doe` | view | 29 | `date` 2001-06-30 to 2005-08-01 |
| `doenames` | view | 6 | `st_date` 2001-06-30 to 2002-11-30 |

## doe_all

| table | rows | columns | dates |
|---|---|---|---|
| `doe` | 7,729,772 | 29 | `date`, not asked (too big) |
| `doenames` | 240 | 6 | `st_date` 2001-06-30 to 2002-11-30 |

## etfg_samp

| table | rows | columns | dates |
|---|---|---|---|
| `analytics` | 294 | 34 | `etfg_date` 2021-11-01 to 2021-11-30 |
| `constituents` | 90,432 | 17 | `etfg_date` 2021-11-01 to 2021-12-01 |
| `fund_flow` | 270 | 6 | `etfg_date` 2021-11-01 to 2021-11-30 |
| `industry` | 273 | 56 | `etfg_date` 2021-11-01 to 2021-11-30 |

## etfgsamp

| table | rows | columns | dates |
|---|---|---|---|
| `analytics` | view | 34 | `etfg_date` 2021-11-01 to 2021-11-30 |
| `constituents` | view | 17 | `etfg_date` 2021-11-01 to 2021-12-01 |
| `fund_flow` | view | 6 | `etfg_date` 2021-11-01 to 2021-11-30 |
| `industry` | view | 56 | `etfg_date` 2021-11-01 to 2021-11-30 |

## execcomp

| table | rows | columns | dates |
|---|---|---|---|
| `anncomp` | view | 107 | `becameceo` 1945-01-01 to 2026-10-26 |
| `codirfin` | view | 71 | `srcdate` 1992-03-31 to 2026-09-29 |
| `colev` | view | 18 | - |
| `coperol` | view | 14 | `becameceo` 1945-01-01 to 2026-10-26 |
| `deferredcomp` | view | 46 | `becameceo` 1960-01-01 to 2026-10-26 |
| `directorcomp` | view | 28 | - |
| `ex_black` | view | 6 | - |
| `ex_header` | view | 38 | `becameceo` 1945-01-01 to 2026-10-26 |
| `exnames` | view | 5 | - |
| `ltawdtab` | view | 48 | `becameceo` 1950-01-01 to 2025-07-14 |
| `outstandingawards` | view | 50 | `exdate` 1930-01-02 to 2044-04-21 |
| `pension` | view | 44 | `becameceo` 1951-01-01 to 2026-10-26 |
| `person` | view | 8 | - |
| `planbasedawards` | view | 53 | `grant_date` 1905-07-07 to 2406-10-01 |
| `stgrttab` | view | 49 | `exdate` 1992-10-01 to 2025-12-16 |

## factsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `funds` | 154 | 16 | `current_report_date` 1999-12-31 to 2013-06-28 |
| `monthly_prices_final_int` | 30,000 | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `monthly_prices_final_int_sample` | 30,000 | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `monthly_prices_final_usc` | 29,520 | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `monthly_prices_final_usc_sample` | 29,520 | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `wrds_fund_af_int` | 1,376 | 693 | `date` 1980-06-30 to 2011-03-31 |
| `wrds_fund_af_int_sample` | 1,376 | 693 | `date` 1980-06-30 to 2011-03-31 |
| `wrds_fund_af_usc` | 1,733 | 693 | `date` 1980-06-30 to 2011-07-31 |
| `wrds_fund_af_usc_sample` | 1,733 | 693 | `date` 1980-06-30 to 2011-07-31 |
| `wrds_fund_ltm_int` | 1,562 | 225 | `date` 2003-06-30 to 2011-06-30 |
| `wrds_fund_ltm_int_sample` | 1,562 | 225 | `date` 2003-06-30 to 2011-06-30 |
| `wrds_fund_ltm_usc` | 2,044 | 225 | `date` 2003-05-31 to 2011-08-31 |
| `wrds_fund_ltm_usc_sample` | 2,044 | 225 | `date` 2003-05-31 to 2011-08-31 |
| `wrds_fund_qf_int` | 2,292 | 464 | `date` 2000-03-31 to 2011-06-30 |
| `wrds_fund_qf_int_sample` | 2,292 | 464 | `date` 2000-03-31 to 2011-06-30 |
| `wrds_fund_qf_usc` | 3,233 | 464 | `date` 1998-02-28 to 2011-08-31 |
| `wrds_fund_qf_usc_sample` | 3,233 | 464 | `date` 1998-02-28 to 2011-08-31 |
| `wrds_fund_r_af_int` | 43 | 689 | `date` 2003-12-31 to 2009-12-31 |
| `wrds_fund_r_af_int_sample` | 43 | 689 | `date` 2003-12-31 to 2009-12-31 |
| `wrds_fund_r_af_usc` | 74 | 689 | `date` 2003-12-31 to 2010-12-31 |
| `wrds_fund_r_af_usc_sample` | 74 | 689 | `date` 2003-12-31 to 2010-12-31 |
| `wrds_fund_saf_int` | 22 | 457 | `date` 2000-09-30 to 2011-06-30 |
| `wrds_fund_saf_int_sample` | 22 | 457 | `date` 2000-09-30 to 2011-06-30 |
| `wrds_fund_saf_usc` | 6 | 457 | `date` 2008-06-30 to 2010-12-31 |
| `wrds_fund_saf_usc_sample` | 6 | 457 | `date` 2008-06-30 to 2010-12-31 |
| `wrds_institutions` | 60 | 8 | `current_report_date` 2001-02-01 to 2013-06-14 |
| `wrds_unadj_13f_holdings_hist` | 223,677 | 11 | `report_date` 1999-03-31 to 2013-03-31 |
| `wrds_unadj_fund_holdings_hist` | 125,006 | 12 | `report_date` 1999-09-30 to 2013-06-28 |

## factsamp_revere

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 64 | - |
| `wrds_company` | 100 | 27 | `start_` 2014-08-29 to 2015-05-08 |
| `wrds_company_hist` | 1,384 | 27 | `start_` 2003-04-03 to 2015-05-08 |
| `wrds_company_segrev_detail` | 378 | 43 | `start_` 2012-07-11 to 2015-05-11 |
| `wrds_company_segrev_report` | 102 | 14 | `start_` 2012-07-11 to 2015-05-11 |
| `wrds_company_segrev_summary` | 2,967 | 34 | `start_` 2012-07-11 to 2015-05-11 |
| `wrds_geo_exp` | 43,983 | 24 | `start_` 2003-04-01 to 2015-05-09 |
| `wrds_geo_exp_all` | 910,774 | 24 | `start_` 2003-04-01 to 2015-05-09 |
| `wrds_product_merged` | 15,525 | 27 | `start_` 2003-04-03 to 2015-05-11 |
| `wrds_product_sector` | 588,622 | 4 | `start_` 2003-04-03 to 2015-05-11 |
| `wrds_relationship` | 27,026 | 34 | `start_` 2003-04-03 to 2015-05-11 |
| `wrds_sector` | 20,045 | 22 | `start_` 2003-04-03 to 2015-05-08 |

## ff

| table | rows | columns | dates |
|---|---|---|---|
| `factors_china` | view | 5 | `mnthdt` 2000-01-31 to 2018-12-31 |
| `factors_daily` | view | 6 | `date` 1926-07-01 to 2026-09-30 |
| `factors_monthly` | view | 9 | `date` 1926-07-01 to 2026-09-01 |
| `fivefactors_daily` | view | 8 | `date` 1963-07-01 to 2026-09-30 |
| `fivefactors_monthly` | view | 11 | `date` 1963-07-01 to 2026-09-01 |
| `industry12` | view | 5 | - |
| `industry48` | view | 6 | - |
| `liq_ps` | view | 5 | `date` 1962-08-31 to 2025-12-31 |
| `liq_sadka` | view | 4 | `date` 1983-04-29 to 2008-12-31 |
| `portfolios` | view | 33 | `date` 1926-07-31 to 2026-09-30 |
| `portfolios25` | view | 128 | `date` 1926-07-31 to 2026-09-30 |
| `portfolios_d` | view | 25 | `date` 1926-07-01 to 2026-09-30 |

## ff_all

| table | rows | columns | dates |
|---|---|---|---|
| `factors_china` | 228 | 5 | `mnthdt` 2000-01-31 to 2018-12-31 |
| `factors_daily` | 26,338 | 6 | `date` 1926-07-01 to 2026-09-30 |
| `factors_monthly` | 1,203 | 9 | `date` 1926-07-01 to 2026-09-01 |
| `fivefactors_daily` | 15,918 | 8 | `date` 1963-07-01 to 2026-09-30 |
| `fivefactors_monthly` | 759 | 11 | `date` 1963-07-01 to 2026-09-01 |
| `industry12` | view | 5 | - |
| `industry48` | 598 | 6 | - |
| `liq_ps` | 761 | 5 | `date` 1962-08-31 to 2025-12-31 |
| `liq_sadka` | 309 | 4 | `date` 1983-04-29 to 2008-12-31 |
| `portfolios` | 1,203 | 33 | `date` 1926-07-31 to 2026-09-30 |
| `portfolios25` | 1,203 | 128 | `date` 1926-07-31 to 2026-09-30 |
| `portfolios_d` | 26,338 | 25 | `date` 1926-07-01 to 2026-09-30 |

## fisdsamp

| table | rows | columns | dates |
|---|---|---|---|
| `fisd_issue_samp` | view | 66 | `maturity` 2008-05-16 to 2067-05-15 |
| `fisd_issuer_samp` | view | 10 | - |
| `fisd_mergedissue_samp` | view | 224 | `maturity` 2008-05-16 to 2067-05-15 |
| `fisd_mergedissuer_samp` | view | 22 | - |
| `fisd_mergedredemption_samp` | view | 31 | `make_whole_start_date` 2005-03-31 to 2010-12-09 |
| `fisd_ratings_samp` | view | 8 | `rating_date` 2005-01-20 to 2011-04-18 |
| `fisd_tsales_samp` | view | 33 | `trd_exctn_dt` 2005-03-21 to 2010-03-31 |
| `issue_issuer_samp` | view | 75 | `maturity` 1991-06-01 to 2098-01-15 |
| `naic_bond_transactions_samp` | view | 21 | `trans_date` 2005-03-21 to 2010-12-30 |

## fisdsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `fisd_issue_samp` | 58 | 66 | `maturity` 2008-05-16 to 2067-05-15 |
| `fisd_issuer_samp` | 11 | 10 | - |
| `fisd_mergedissue_samp` | 58 | 224 | `maturity` 2008-05-16 to 2067-05-15 |
| `fisd_mergedissuer_samp` | 11 | 22 | - |
| `fisd_mergedredemption_samp` | 40 | 31 | `make_whole_start_date` 2005-03-31 to 2010-12-09 |
| `fisd_ratings_samp` | 386 | 8 | `rating_date` 2005-01-20 to 2011-04-18 |
| `fisd_tsales_samp` | 119,173 | 33 | `trd_exctn_dt` 2005-03-21 to 2010-03-31 |
| `issue_issuer_samp` | 296 | 75 | `maturity` 1991-06-01 to 2098-01-15 |
| `naic_bond_transactions_samp` | 4,578 | 21 | `trans_date` 2005-03-21 to 2010-12-30 |

## fjc

| table | rows | columns | dates |
|---|---|---|---|
| `appeals` | view | 65 | `dktdate` 1954-08-05 to 2026-06-30 |
| `bankruptcy` | view | 89 | `snapshot` 2008-09-30 to 2026-03-31 |
| `civil` | view | 53 | `filedate` 1900-01-01 to 2026-06-30 |
| `criminal` | view | 156 | `filedate` 1899-12-01 to 2026-06-30 |
| `wrds_bankruptcy_link` | view | 4 | - |
| `wrds_civil_link` | view | 13 | `filedate` 1960-08-17 to 2024-12-12 |
| `wrds_criminal_link` | view | 15 | `filedate` 2007-03-14 to 2024-11-20 |

## fjc_linking

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_bankruptcy_link` | 1,414 | 4 | - |
| `wrds_civil_link` | 180,174 | 13 | `filedate` 1960-08-17 to 2024-12-12 |
| `wrds_criminal_link` | 47 | 15 | `filedate` 2007-03-14 to 2024-11-20 |

## fjc_litigation

| table | rows | columns | dates |
|---|---|---|---|
| `appeals` | 2,415,526 | 65 | `dktdate` 1954-08-05 to 2026-06-30 |
| `bankruptcy` | 38,030,840 | 89 | `snapshot`, not asked (too big) |
| `civil` | 13,780,452 | 53 | `filedate`, not asked (too big) |
| `criminal` | 7,743,962 | 156 | `filedate`, not asked (too big) |

## frb

| table | rows | columns | dates |
|---|---|---|---|
| `fx_daily` | view | 49 | `date` 1971-01-04 to 2025-02-07 |
| `fx_monthly` | view | 48 | `date` 1971-01-31 to 2025-01-31 |
| `rates_daily` | view | 83 | `date` 1954-01-04 to 2025-02-13 |
| `rates_monthly` | view | 77 | `date` 1919-01-31 to 2025-02-28 |

## frb_all

| table | rows | columns | dates |
|---|---|---|---|
| `fx_daily` | 14,115 | 49 | `date` 1971-01-04 to 2025-02-07 |
| `fx_monthly` | 649 | 48 | `date` 1971-01-31 to 2025-01-31 |
| `rates_daily` | 25,924 | 83 | `date` 1954-01-04 to 2025-02-13 |
| `rates_monthly` | 1,274 | 77 | `date` 1919-01-31 to 2025-02-28 |

## fssamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 64 | - |
| `funds` | view | 16 | `current_report_date` 1999-12-31 to 2013-06-28 |
| `monthly_prices_final_int` | view | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `monthly_prices_final_int_sample` | view | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `monthly_prices_final_usc` | view | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `monthly_prices_final_usc_sample` | view | 18 | `price_date` 1991-09-30 to 2011-08-31 |
| `wrds_company` | view | 27 | `start_` 2014-08-29 to 2015-05-08 |
| `wrds_company_hist` | view | 27 | `start_` 2003-04-03 to 2015-05-08 |
| `wrds_company_segrev_detail` | view | 43 | `start_` 2012-07-11 to 2015-05-11 |
| `wrds_company_segrev_report` | view | 14 | `start_` 2012-07-11 to 2015-05-11 |
| `wrds_company_segrev_summary` | view | 34 | `start_` 2012-07-11 to 2015-05-11 |
| `wrds_fund_af_int` | view | 693 | `date` 1980-06-30 to 2011-03-31 |
| `wrds_fund_af_int_sample` | view | 693 | `date` 1980-06-30 to 2011-03-31 |
| `wrds_fund_af_usc` | view | 693 | `date` 1980-06-30 to 2011-07-31 |
| `wrds_fund_af_usc_sample` | view | 693 | `date` 1980-06-30 to 2011-07-31 |
| `wrds_fund_ltm_int` | view | 225 | `date` 2003-06-30 to 2011-06-30 |
| `wrds_fund_ltm_int_sample` | view | 225 | `date` 2003-06-30 to 2011-06-30 |
| `wrds_fund_ltm_usc` | view | 225 | `date` 2003-05-31 to 2011-08-31 |
| `wrds_fund_ltm_usc_sample` | view | 225 | `date` 2003-05-31 to 2011-08-31 |
| `wrds_fund_qf_int` | view | 464 | `date` 2000-03-31 to 2011-06-30 |
| `wrds_fund_qf_int_sample` | view | 464 | `date` 2000-03-31 to 2011-06-30 |
| `wrds_fund_qf_usc` | view | 464 | `date` 1998-02-28 to 2011-08-31 |
| `wrds_fund_qf_usc_sample` | view | 464 | `date` 1998-02-28 to 2011-08-31 |
| `wrds_fund_r_af_int` | view | 689 | `date` 2003-12-31 to 2009-12-31 |
| `wrds_fund_r_af_int_sample` | view | 689 | `date` 2003-12-31 to 2009-12-31 |
| `wrds_fund_r_af_usc` | view | 689 | `date` 2003-12-31 to 2010-12-31 |
| `wrds_fund_r_af_usc_sample` | view | 689 | `date` 2003-12-31 to 2010-12-31 |
| `wrds_fund_saf_int` | view | 457 | `date` 2000-09-30 to 2011-06-30 |
| `wrds_fund_saf_int_sample` | view | 457 | `date` 2000-09-30 to 2011-06-30 |
| `wrds_fund_saf_usc` | view | 457 | `date` 2008-06-30 to 2010-12-31 |
| `wrds_fund_saf_usc_sample` | view | 457 | `date` 2008-06-30 to 2010-12-31 |
| `wrds_geo_exp` | view | 24 | `start_` 2003-04-01 to 2015-05-09 |
| `wrds_geo_exp_all` | view | 24 | `start_` 2003-04-01 to 2015-05-09 |
| `wrds_institutions` | view | 8 | `current_report_date` 2001-02-01 to 2013-06-14 |
| `wrds_product_merged` | view | 27 | `start_` 2003-04-03 to 2015-05-11 |
| `wrds_product_sector` | view | 4 | `start_` 2003-04-03 to 2015-05-11 |
| `wrds_relationship` | view | 34 | `start_` 2003-04-03 to 2015-05-11 |
| `wrds_sector` | view | 22 | `start_` 2003-04-03 to 2015-05-08 |
| `wrds_unadj_13f_holdings_hist` | view | 11 | `report_date` 1999-03-31 to 2013-03-31 |
| `wrds_unadj_fund_holdings_hist` | view | 12 | `report_date` 1999-09-30 to 2013-06-28 |

## ftsesamp

| table | rows | columns | dates |
|---|---|---|---|
| `ctr_monthly_us` | view | 48 | `effective_date` 2008-08-29 to 2017-09-29 |
| `idx_holdings_us` | view | 46 | `date` 2008-09-30 to 2017-09-29 |
| `rgs_sw_us` | view | 23 | `effective_date` 1996-07-31 to 2017-09-29 |

## ftsesamp_russell_us

| table | rows | columns | dates |
|---|---|---|---|
| `ctr_monthly_us` | 1,040 | 48 | `effective_date` 2008-08-29 to 2017-09-29 |
| `idx_holdings_us` | 20,320 | 46 | `date` 2008-09-30 to 2017-09-29 |
| `rgs_sw_us` | 24,051 | 23 | `effective_date` 1996-07-31 to 2017-09-29 |

## gutenberg

| table | rows | columns | dates |
|---|---|---|---|
| `gutenberg_book` | 3,020 | 5 | - |

## hfrsamp

| table | rows | columns | dates |
|---|---|---|---|
| `asset` | view | 3 | `date` 1988-12-31 to 2009-12-31 |
| `fund` | view | 59 | `inception` 1984-07-01 to 2011-09-01 |
| `hfri_const` | view | 3 | - |
| `hfrx_const` | view | 3 | - |
| `instrument` | view | 6 | `date` 1996-12-31 to 2009-12-31 |
| `region` | view | 6 | `date` 1996-08-22 to 2009-12-31 |
| `ror` | view | 4 | `date` 1984-07-31 to 2009-12-31 |

## hfrsamp_hfrdb

| table | rows | columns | dates |
|---|---|---|---|
| `asset` | 5,232 | 3 | `date` 1988-12-31 to 2009-12-31 |
| `fund` | 100 | 59 | `inception` 1984-07-01 to 2011-09-01 |
| `hfri_const` | 70 | 3 | - |
| `hfrx_const` | 54 | 3 | - |
| `instrument` | 874 | 6 | `date` 1996-12-31 to 2009-12-31 |
| `region` | 825 | 6 | `date` 1996-08-22 to 2009-12-31 |
| `ror` | 6,864 | 4 | `date` 1984-07-31 to 2009-12-31 |

## ibessamp_kpi

| table | rows | columns | dates |
|---|---|---|---|
| `act_kpiint` | 8,150 | 18 | `fpenddate` 2009-01-01 to 2017-01-01 |
| `act_kpius` | 96,196 | 18 | `fpenddate` 2002-12-01 to 2017-03-01 |
| `chars` | view (empty) | 7 | - |
| `companies` | 242 | 18 | `startdate` 1976-01-15 to 2017-02-16 |
| `det_kpiint` | 12,469 | 21 | `actdate` 2012-10-16 to 2017-04-20 |
| `det_kpius` | 311,879 | 21 | `actdate` 2012-05-25 to 2017-04-20 |
| `measures` | 393 | 7 | - |
| `statsum_kpiint` | 11,335 | 21 | `fpenddate` 2020-12-01 to 2020-12-01 |
| `statsum_kpius` | 236,290 | 21 | `fpenddate` 2020-12-01 to 2020-12-01 |

## ifgrsamp

| table | rows | columns | dates |
|---|---|---|---|
| `abi_ticker_map` | view | 3 | - |
| `business` | view | 54 | - |
| `business_chars` | view (empty) | 52 | - |
| `residential` | view | 67 | - |

## ims_obp_trial

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 145 | `change`, not asked |
| `obp_premium` | 50 | 145 | `change` 2015-11-17 to 2016-11-03 |

## imssamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 145 | `change`, not asked |
| `obp_premium` | view | 145 | `change` 2015-11-17 to 2016-11-03 |

## infasamp

| table | rows | columns | dates |
|---|---|---|---|
| `contract_organization_sample` | view | 5 | - |
| `contract_sample` | view | 14 | `date` 1965-02-02 to 2025-03-24 |
| `key_values_sample` | view | 6 | - |
| `organization_sample` | view | 9 | - |
| `project_sample` | view | 12 | - |

## infogroupsamp_business

| table | rows | columns | dates |
|---|---|---|---|
| `abi_ticker_map` | 7,196 | 3 | - |
| `business` | 1,314 | 54 | - |
| `business_chars` | view (empty) | 52 | - |

## infogroupsamp_residential

| table | rows | columns | dates |
|---|---|---|---|
| `residential` | 100 | 67 | - |

## infraclear_samp

| table | rows | columns | dates |
|---|---|---|---|
| `contract_organization_sample` | 545 | 5 | - |
| `contract_sample` | 125 | 14 | `date` 1965-02-02 to 2025-03-24 |
| `key_values_sample` | 42,651 | 6 | - |
| `organization_sample` | 1,000 | 9 | - |
| `project_sample` | 1,000 | 12 | - |

## insdsamp

| table | rows | columns | dates |
|---|---|---|---|
| `fdic_derivatives` | view | 27 | `filing_date` 2023-07-26 to 2023-09-29 |
| `fdic_document_info` | view | 18 | `filing_date` 2023-07-03 to 2023-09-29 |
| `fdic_footnotes` | view | 5 | `filing_date` 2023-07-03 to 2023-09-25 |
| `fdic_nonderivatives` | view | 20 | `filing_date` 2023-07-03 to 2023-09-29 |
| `fdic_reporting_owners` | view | 18 | `filing_date` 2023-07-03 to 2023-09-29 |
| `fdic_signatures` | view | 8 | `filing_date` 2023-07-03 to 2023-09-29 |
| `sec_derivatives` | view | 28 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_document_info` | view | 24 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_footnotes` | view | 11 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_nonderivatives` | view | 21 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_reporting_owners` | view | 21 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_signatures` | view | 6 | `signaturedate` 2023-09-01 to 2023-09-01 |
| `secbert_footnotes` | view | 27 | `fdate` 2023-09-01 to 2023-09-01 |
| `wrds_nara_filings` | view | 31 | `filing_date` 2001-03-12 to 2001-03-12 |
| `wrds_table_1` | view | 62 | `filing_date` 2023-07-03 to 2023-09-29 |
| `wrds_table_2` | view | 69 | `filing_date` 2023-07-26 to 2023-09-29 |
| `wrds_table_3` | view | 44 | `filing_date` 2023-09-01 to 2023-09-05 |

## iri

| table | rows | columns | dates |
|---|---|---|---|
| `db1983` | view | 53 | - |
| `db1984` | view | 53 | - |
| `db1985` | view | 53 | - |
| `db1986` | view | 53 | - |
| `db1987` | view | 53 | - |
| `db1988` | view | 53 | - |
| `db1989` | view | 53 | - |
| `db1990` | view | 53 | - |
| `db1991` | view | 53 | - |
| `db1992` | view | 53 | - |
| `db1993` | view | 53 | - |
| `db1994` | view | 53 | - |
| `db1995` | view | 53 | - |
| `db1996` | view | 53 | - |
| `db1997` | view | 53 | - |

## iri_all

| table | rows | columns | dates |
|---|---|---|---|
| `db1983` | 9,655 | 53 | - |
| `db1984` | 9,261 | 53 | - |
| `db1985` | 9,328 | 53 | - |
| `db1986` | 13,323 | 53 | - |
| `db1987` | 13,380 | 53 | - |
| `db1988` | 13,506 | 53 | - |
| `db1989` | 13,865 | 53 | - |
| `db1990` | 13,599 | 53 | - |
| `db1991` | 13,781 | 53 | - |
| `db1992` | 14,447 | 53 | - |
| `db1993` | 14,415 | 53 | - |
| `db1994` | 14,336 | 53 | - |
| `db1995` | 17,182 | 53 | - |
| `db1996` | 17,059 | 53 | - |
| `db1997` | 16,765 | 53 | - |

## iss

| table | rows | columns | dates |
|---|---|---|---|
| `climate_emissions` | view | 27 | - |
| `committee_detail` | view | 26 | `start_date` 1900-01-01 to 3124-10-01 |
| `company_diversity` | view | 84 | `from_date` 2002-12-27 to 2026-09-30 |
| `director_roles` | view | 120 | `director_start_date` 1900-01-01 to 2121-03-01 |
| `person_ethnicity` | view | 17 | `birth_date` 1900-01-01 to 2013-01-01 |
| `symbology` | view | 24 | `ipo_date` 1900-01-01 to 2026-05-27 |

## iss_climate_emissions

| table | rows | columns | dates |
|---|---|---|---|
| `climate_emissions` | 121,357 | 27 | - |

## iss_directors_global

| table | rows | columns | dates |
|---|---|---|---|
| `committee_detail` | 8,386,879 | 26 | `start_date`, not asked (too big) |
| `company_diversity` | 597,148 | 84 | `from_date` 2002-12-27 to 2026-09-30 |
| `director_roles` | 4,906,076 | 120 | `director_start_date` 1900-01-01 to 2121-03-01 |
| `person_ethnicity` | 449,161 | 17 | `birth_date` 1900-01-01 to 2013-01-01 |
| `symbology` | 38,715 | 24 | `ipo_date` 1900-01-01 to 2026-05-27 |

## iss_va_mf

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_mf` | view (empty) | 76 | `meetingdate`, not asked |
| `mf_company_names` | 42,629 | 2 | - |
| `mf_institution_names` | 899 | 2 | - |
| `voteanalysis_npx` | 238,529,088 | 30 | `meetingdate`, not asked (too big) |

## iss_va_shareholder

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_pro` | view (empty) | 76 | `meetingdate`, not asked |
| `va_proposals` | 20,867 | 28 | `meeting_date` 2006-01-01 to 2025-12-29 |

## iss_va_vote_global

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_glob` | view (empty) | 76 | `meetingdate`, not asked |
| `globalvoteresults` | 3,987,694 | 41 | `meetingdate` 2013-01-02 to 2025-12-31 |

## iss_va_vote_us

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_us` | view (empty) | 76 | `meetingdate`, not asked |
| `vavoteresults` | 887,341 | 29 | `recorddate` 2002-02-26 to 2025-12-21 |

## kpisamp

| table | rows | columns | dates |
|---|---|---|---|
| `act_kpiint` | view | 18 | `fpenddate` 2009-01-01 to 2017-01-01 |
| `act_kpius` | view | 18 | `fpenddate` 2002-12-01 to 2017-03-01 |
| `chars` | view (empty) | 7 | - |
| `companies` | view | 18 | `startdate` 1976-01-15 to 2017-02-16 |
| `det_kpiint` | view | 21 | `actdate` 2012-10-16 to 2017-04-20 |
| `det_kpius` | view | 21 | `actdate` 2012-05-25 to 2017-04-20 |
| `measures` | view | 7 | - |
| `statsum_kpiint` | view | 21 | `fpenddate` 2020-12-01 to 2020-12-01 |
| `statsum_kpius` | view | 21 | `fpenddate` 2020-12-01 to 2020-12-01 |

## macrofin

| table | rows | columns | dates |
|---|---|---|---|
| `cay` | view | 5 | `date` 1952-01-01 to 2019-03-01 |
| `financial_uncertainty` | view | 4 | `date` 1960-07-01 to 2019-12-01 |
| `fxdata` | view | 7 | - |
| `importportfolios` | view | 7 | - |
| `macro_uncertainty` | view | 4 | `date` 1960-07-01 to 2019-12-01 |
| `port_eg_annual` | view | 6 | - |
| `port_eg_daily` | view | 6 | `date` 1967-01-03 to 2019-12-31 |
| `port_eg_monthly` | view | 7 | - |
| `port_eg_quarterly` | view | 7 | - |
| `port_eg_weekly` | view | 6 | `date` 1967-01-06 to 2019-12-27 |
| `port_eg_weekly_w2w` | view | 6 | `date` 1967-01-11 to 2019-12-31 |
| `port_ia_roe_annual` | view | 6 | - |
| `port_ia_roe_daily` | view | 6 | `date` 1967-01-03 to 2019-12-31 |
| `port_ia_roe_monthly` | view | 7 | - |
| `port_ia_roe_quarterly` | view | 7 | - |
| `port_ia_roe_weekly` | view | 6 | `date` 1967-01-06 to 2019-12-27 |
| `port_ia_roe_weekly_w2w` | view | 6 | `date` 1967-01-11 to 2019-12-31 |
| `q_factors_annual` | view | 7 | - |
| `q_factors_daily` | view | 7 | `date` 1967-01-03 to 2019-12-31 |
| `q_factors_monthly` | view | 8 | - |
| `q_factors_quarterly` | view | 8 | - |
| `q_factors_weekly` | view | 7 | `date` 1967-01-06 to 2019-12-27 |
| `q_factors_weekly_w2w` | view | 7 | `date` 1967-01-11 to 2019-12-31 |
| `tradedata` | view | 9 | - |

## macrofin_comm_trade

| table | rows | columns | dates |
|---|---|---|---|
| `cay` | 271 | 5 | `date` 1952-01-01 to 2019-03-01 |
| `financial_uncertainty` | 714 | 4 | `date` 1960-07-01 to 2019-12-01 |
| `fxdata` | 4,230 | 7 | - |
| `importportfolios` | 304 | 7 | - |
| `macro_uncertainty` | 714 | 4 | `date` 1960-07-01 to 2019-12-01 |
| `port_eg_annual` | 318 | 6 | - |
| `port_eg_daily` | 80,040 | 6 | `date` 1967-01-03 to 2019-12-31 |
| `port_eg_monthly` | 3,816 | 7 | - |
| `port_eg_quarterly` | 1,272 | 7 | - |
| `port_eg_weekly` | 16,590 | 6 | `date` 1967-01-06 to 2019-12-27 |
| `port_eg_weekly_w2w` | 16,590 | 6 | `date` 1967-01-11 to 2019-12-31 |
| `port_ia_roe_annual` | 954 | 6 | - |
| `port_ia_roe_daily` | 240,120 | 6 | `date` 1967-01-03 to 2019-12-31 |
| `port_ia_roe_monthly` | 11,448 | 7 | - |
| `port_ia_roe_quarterly` | 3,816 | 7 | - |
| `port_ia_roe_weekly` | 49,770 | 6 | `date` 1967-01-06 to 2019-12-27 |
| `port_ia_roe_weekly_w2w` | 49,770 | 6 | `date` 1967-01-11 to 2019-12-31 |
| `q_factors_annual` | 53 | 7 | - |
| `q_factors_daily` | 13,340 | 7 | `date` 1967-01-03 to 2019-12-31 |
| `q_factors_monthly` | 636 | 8 | - |
| `q_factors_quarterly` | 212 | 8 | - |
| `q_factors_weekly` | 2,765 | 7 | `date` 1967-01-06 to 2019-12-27 |
| `q_factors_weekly_w2w` | 2,765 | 7 | `date` 1967-01-11 to 2019-12-31 |
| `tradedata` | 1,518 | 9 | - |

## midas

| table | rows | columns | dates |
|---|---|---|---|
| `security` | view | 26 | `date` 2012-01-03 to 2025-12-31 |

## morningstarsamp_cisdm

| table | rows | columns | dates |
|---|---|---|---|
| `active_fund_info` | 50 | 142 | `na_date` 2011-12-31 to 2013-08-13 |
| `active_returns_assets` | 11,700 | 5 | `date` 1994-01-31 to 2013-06-30 |

## mpsych_sample

| table | rows | columns | dates |
|---|---|---|---|
| `sample` | 434,390 | 515 | `date` 1998-01-01 to 2024-10-20 |

## mrktsamp

| table | rows | columns | dates |
|---|---|---|---|
| `amereqty2011` | view | 57 | `datadate` 2011-03-21 to 2011-03-21 |
| `amereqtyi2011` | view | 93 | `datadate` 2011-03-21 to 2011-03-21 |
| `cds2011` | view | 163 | `date` 2011-03-21 to 2011-03-21 |
| `cdxcomps` | view | 85 | `date` 2011-03-21 to 2011-03-21 |
| `cdxconst` | view | 34 | `date` 2021-05-27 to 2021-05-27 |
| `corpbond2011` | view | 93 | `datadate` 2011-03-21 to 2011-03-21 |
| `corporatebonds2011` | view | 57 | `datadate` 2011-03-21 to 2011-03-21 |
| `redent` | view | 17 | `recorddate` 2007-06-15 to 2014-09-08 |
| `redentaucccy` | view | 10 | `defaultdate` 2009-12-24 to 2015-08-03 |
| `redentcorpact` | view | 6 | `eventdate` 2011-06-01 to 2018-04-02 |
| `redentcredauc` | view | 18 | `defaultdate` 2009-12-24 to 2015-08-03 |
| `redentisda` | view | 3 | - |
| `redentlookup` | view | 6 | - |
| `redentrating` | view | 3 | - |
| `redentsuccession` | view | 9 | `eventdate_succession` 2011-06-01 to 2026-04-24 |
| `redobl` | view | 12 | `maturity` 2006-06-01 to 2032-06-01 |
| `redoblindxconst` | view | 4 | - |
| `redobllookup` | view | 6 | - |
| `redoblprospectus` | view | 4 | - |
| `redoblrefentity` | view | 15 | `pairvalidfrom` 2005-11-18 to 2011-06-01 |

## mrktsamp_cds

| table | rows | columns | dates |
|---|---|---|---|
| `cds2011` | 113,640 | 163 | `date` 2011-03-21 to 2011-03-21 |

## mrktsamp_cdx

| table | rows | columns | dates |
|---|---|---|---|
| `cdxcomps` | 1,251 | 85 | `date` 2011-03-21 to 2011-03-21 |
| `cdxconst` | 628 | 34 | `date` 2021-05-27 to 2021-05-27 |

## mrktsamp_msf

| table | rows | columns | dates |
|---|---|---|---|
| `amereqty2011` | 9,441 | 57 | `datadate` 2011-03-21 to 2011-03-21 |
| `amereqtyi2011` | 16,359 | 93 | `datadate` 2011-03-21 to 2011-03-21 |
| `corpbond2011` | 65,614 | 93 | `datadate` 2011-03-21 to 2011-03-21 |
| `corporatebonds2011` | 54,963 | 57 | `datadate` 2011-03-21 to 2011-03-21 |

## mrktsamp_red

| table | rows | columns | dates |
|---|---|---|---|
| `redent` | 8 | 17 | `recorddate` 2007-06-15 to 2014-09-08 |
| `redentaucccy` | 11 | 10 | `defaultdate` 2009-12-24 to 2015-08-03 |
| `redentcorpact` | 12 | 6 | `eventdate` 2011-06-01 to 2018-04-02 |
| `redentcredauc` | 5 | 18 | `defaultdate` 2009-12-24 to 2015-08-03 |
| `redentisda` | 6 | 3 | - |
| `redentlookup` | 8 | 6 | - |
| `redentrating` | 10 | 3 | - |
| `redentsuccession` | 8 | 9 | `eventdate_succession` 2011-06-01 to 2026-04-24 |
| `redobl` | 31 | 12 | `maturity` 2006-06-01 to 2032-06-01 |
| `redoblindxconst` | 5 | 4 | - |
| `redobllookup` | 30 | 6 | - |
| `redoblprospectus` | 33 | 4 | - |
| `redoblrefentity` | 33 | 15 | `pairvalidfrom` 2005-11-18 to 2011-06-01 |

## msci_climate_samp

| table | rows | columns | dates |
|---|---|---|---|
| `capex` | 7 | 26 | - |
| `carbon_emiss_n_ener_use` | 68 | 58 | `evic_fiscal_year_end_date` 2024-06-30 to 2025-05-31 |
| `carbon_emiss_scope_3_est` | 52 | 67 | - |
| `climate_change_targ_n_commit` | 147 | 34 | `target_carbon_announcement_date` 2015-01-01 to 2024-06-06 |
| `climate_change_targ_n_commit_sum` | 45 | 32 | `sbti_update_date` 2015-06-01 to 2024-09-26 |
| `country_climate_change_data` | 3 | 80 | - |
| `country_climate_change_data_ts` | 3 | 53 | - |
| `emissions_intensity_ts` | 67 | 81 | `evic_quarter_end_date_ts` 2024-09-30 to 2024-12-31 |
| `environmental_impact_revenue` | 52 | 55 | - |
| `fossil_fuel_prod_n_res` | 64 | 150 | - |
| `low_carbon_patents` | 9 | 66 | - |
| `low_carbon_transition_scores` | 24 | 6 | - |
| `power_generation_n_capacity` | 12 | 26 | - |
| `prod_based_emiss_intensities` | 3 | 66 | - |
| `prod_based_emiss_intensities_ts` | 15 | 54 | - |
| `supplemental_carbon_emissions` | 4 | 29 | `car_emi_evi_usd_scp12_int_q_p_d` 2024-11-06 to 2024-11-06 |

## msci_common_samp

| table | rows | columns | dates |
|---|---|---|---|
| `mast_instrument_ref_wcuse` | 12,683 | 17 | `as_of_date` 2026-04-30 to 2026-04-30 |
| `mast_issuer_ref` | 81 | 87 | `as_of_date` 2026-04-30 to 2026-04-30 |
| `msci_metadata` | 2,459 | 17 | `start_date` 1999-08-31 to 2025-06-05 |

## msci_esg_samp

| table | rows | columns | dates |
|---|---|---|---|
| `agm_data` | 59 | 19 | `gm_prop_annualmtgdate` 2020-01-23 to 2020-12-17 |
| `comp_env_qual_inds` | 30 | 146 | - |
| `comp_soc_n_corp_beh_qual_inds` | 61 | 213 | - |
| `controversies` | 67 | 125 | - |
| `derived_esg_metrics` | 62 | 206 | - |
| `drill_down` | 72 | 416 | - |
| `governance_data` | 67 | 114 | - |
| `msci_esg_ratings` | 3,584 | 249 | `as_of_date` 2020-01-01 to 2024-06-01 |
| `nat_cap_n_pol` | 44 | 37 | - |
| `soc_n_corp_beh` | 40 | 8 | - |
| `summary_scores` | 69 | 250 | `assessment_change_date` 2020-02-28 to 2020-11-02 |
| `workforce_and_diversity` | 72 | 87 | - |

## mscicoms

| table | rows | columns | dates |
|---|---|---|---|
| `mast_instrument_ref_wcuse` | view | 17 | `as_of_date` 2026-04-30 to 2026-04-30 |
| `mast_issuer_ref` | view | 87 | `as_of_date` 2026-04-30 to 2026-04-30 |
| `msci_metadata` | view | 17 | `start_date` 1999-08-31 to 2025-06-05 |

## mscicsmp

| table | rows | columns | dates |
|---|---|---|---|
| `capex` | view | 26 | - |
| `carbon_emiss_n_ener_use` | view | 58 | `evic_fiscal_year_end_date` 2024-06-30 to 2025-05-31 |
| `carbon_emiss_scope_3_est` | view | 67 | - |
| `climate_change_targ_n_commit` | view | 34 | `target_carbon_announcement_date` 2015-01-01 to 2024-06-06 |
| `climate_change_targ_n_commit_sum` | view | 32 | `sbti_update_date` 2015-06-01 to 2024-09-26 |
| `country_climate_change_data` | view | 80 | - |
| `country_climate_change_data_ts` | view | 53 | - |
| `emissions_intensity_ts` | view | 81 | `evic_quarter_end_date_ts` 2024-09-30 to 2024-12-31 |
| `environmental_impact_revenue` | view | 55 | - |
| `fossil_fuel_prod_n_res` | view | 150 | - |
| `low_carbon_patents` | view | 66 | - |
| `low_carbon_transition_scores` | view | 6 | - |
| `power_generation_n_capacity` | view | 26 | - |
| `prod_based_emiss_intensities` | view | 66 | - |
| `prod_based_emiss_intensities_ts` | view | 54 | - |
| `supplemental_carbon_emissions` | view | 29 | `car_emi_evi_usd_scp12_int_q_p_d` 2024-11-06 to 2024-11-06 |

## msciesmp

| table | rows | columns | dates |
|---|---|---|---|
| `agm_data` | view | 19 | `gm_prop_annualmtgdate` 2020-01-23 to 2020-12-17 |
| `comp_env_qual_inds` | view | 146 | - |
| `comp_soc_n_corp_beh_qual_inds` | view | 213 | - |
| `controversies` | view | 125 | - |
| `derived_esg_metrics` | view | 206 | - |
| `drill_down` | view | 416 | - |
| `governance_data` | view | 114 | - |
| `msci_esg_ratings` | view | 249 | `as_of_date` 2020-01-01 to 2024-06-01 |
| `nat_cap_n_pol` | view | 37 | - |
| `soc_n_corp_beh` | view | 8 | - |
| `summary_scores` | view | 250 | `assessment_change_date` 2020-02-28 to 2020-11-02 |
| `workforce_and_diversity` | view | 87 | - |

## msrb

| table | rows | columns | dates |
|---|---|---|---|
| `msrb` | view | 25 | `dated_date` 1930-01-01 to 2027-12-01 |
| `msrb_lookup` | view | 4 | `st_date` 2005-01-03 to 2026-06-30 |
| `msrb_qvards` | view (empty) | 25 | `dated_date`, not asked |

## msrb_all

| table | rows | columns | dates |
|---|---|---|---|
| `msrb` | 224,194,400 | 25 | `dated_date`, not asked (too big) |
| `msrb_lookup` | 397,147 | 4 | `st_date` 2005-01-03 to 2026-06-30 |
| `msrb_qvards` | view (empty) | 25 | `dated_date`, not asked |

## msrbsamp

| table | rows | columns | dates |
|---|---|---|---|
| `msrb_trial` | view | 21 | `dated_date` 1963-09-01 to 2015-04-07 |

## msrbsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `msrb_trial` | 84,163 | 21 | `dated_date` 1963-09-01 to 2015-04-07 |

## niq_samp

| table | rows | columns | dates |
|---|---|---|---|
| `food_bev_divisions` | 345 | 12 | `period_end_date` 2024-01-27 to 2024-01-27 |
| `food_bev_smm` | 984 | 12 | `period_end_date` 2024-01-27 to 2024-01-27 |
| `food_bev_states` | 551 | 12 | `period_end_date` 2024-01-27 to 2024-01-27 |
| `food_bev_total` | 63 | 12 | `period_end_date` 2024-01-27 to 2024-01-27 |
| `prdc_food_bev` | 100 | 8 | - |
| `prod_attr_esg` | 100 | 20 | `period_end_date` 2026-04-25 to 2026-08-22 |

## omtrial

| table | rows | columns | dates |
|---|---|---|---|
| `distrd` | view | 15 | `record_date` 2014-05-12 to 2019-08-12 |
| `distribution` | view | 12 | `declaredate` 2012-03-20 to 2012-03-20 |
| `exchgd` | view | 7 | `effect_date` 1996-01-01 to 1996-01-01 |
| `historical_volatility` | view | 5 | `date` 2013-03-01 to 2013-03-15 |
| `hvold2014` | view | 4 | `date` 2014-03-03 to 2014-03-14 |
| `opinfd` | view | 4 | - |
| `opprcd2014` | view | 22 | `date` 2014-03-03 to 2014-03-14 |
| `option_history` | view | 14 | `expiration` 2010-10-15 to 2018-12-21 |
| `option_price_2013` | view | 24 | `date` 2013-03-01 to 2013-03-15 |
| `optionmeurnames` | view | 8 | `effectivedate` 2010-10-11 to 2010-10-11 |
| `opvold` | view | 5 | `date` 2014-03-03 to 2014-03-14 |
| `secnmd` | view | 8 | `effect_date` 1996-01-02 to 2007-01-11 |
| `secprd` | view | 11 | `date` 2014-03-03 to 2014-03-14 |
| `secprd2014` | view | 11 | `date` 2014-03-03 to 2014-03-14 |
| `securd1` | view | 10 | - |
| `security_name` | view | 6 | `effectivedate` 2010-10-11 to 2010-10-11 |
| `security_price` | view | 14 | `date` 2013-03-01 to 2013-03-15 |
| `std_option_price_2013` | view | 13 | `date` 2013-03-01 to 2013-03-15 |
| `stdopd2014` | view | 12 | `date` 2014-03-03 to 2014-03-14 |
| `tick_option_price_2013` | view | 24 | `date` 2013-03-01 to 2013-03-15 |
| `tick_std_option_price_2013` | view | 13 | `date` 2013-03-01 to 2013-03-15 |
| `tick_volatility_surface_2013` | view | 10 | `date` 2013-03-01 to 2013-03-15 |
| `volatility_surface_2013` | view | 10 | `date` 2013-03-01 to 2013-03-15 |
| `vsurfd2014` | view | 9 | `date` 2014-03-03 to 2014-03-14 |

## optionmsamp_europe

| table | rows | columns | dates |
|---|---|---|---|
| `distribution` | 1 | 12 | `declaredate` 2012-03-20 to 2012-03-20 |
| `historical_volatility` | 143 | 5 | `date` 2013-03-01 to 2013-03-15 |
| `option_history` | 4,990 | 14 | `expiration` 2010-10-15 to 2018-12-21 |
| `option_price_2013` | 8,740 | 24 | `date` 2013-03-01 to 2013-03-15 |
| `optionmeurnames` | 10,036 | 8 | `effectivedate` 2010-10-11 to 2010-10-11 |
| `security_name` | 1 | 6 | `effectivedate` 2010-10-11 to 2010-10-11 |
| `security_price` | 50 | 14 | `date` 2013-03-01 to 2013-03-15 |
| `std_option_price_2013` | 220 | 13 | `date` 2013-03-01 to 2013-03-15 |
| `tick_option_price_2013` | 8,740 | 24 | `date` 2013-03-01 to 2013-03-15 |
| `tick_std_option_price_2013` | 220 | 13 | `date` 2013-03-01 to 2013-03-15 |
| `tick_volatility_surface_2013` | 2,860 | 10 | `date` 2013-03-01 to 2013-03-15 |
| `volatility_surface_2013` | 2,860 | 10 | `date` 2013-03-01 to 2013-03-15 |

## optionmsamp_us

| table | rows | columns | dates |
|---|---|---|---|
| `distrd` | 23 | 15 | `record_date` 2014-05-12 to 2019-08-12 |
| `exchgd` | 1 | 7 | `effect_date` 1996-01-01 to 1996-01-01 |
| `hvold2014` | 130 | 4 | `date` 2014-03-03 to 2014-03-14 |
| `opinfd` | 1 | 4 | - |
| `opprcd2014` | 36,786 | 22 | `date` 2014-03-03 to 2014-03-14 |
| `opvold` | 30 | 5 | `date` 2014-03-03 to 2014-03-14 |
| `secnmd` | 3 | 8 | `effect_date` 1996-01-02 to 2007-01-11 |
| `secprd` | 10 | 11 | `date` 2014-03-03 to 2014-03-14 |
| `secprd2014` | 10 | 11 | `date` 2014-03-03 to 2014-03-14 |
| `securd1` | 1 | 10 | - |
| `stdopd2014` | 180 | 12 | `date` 2014-03-03 to 2014-03-14 |
| `vsurfd2014` | 2,600 | 9 | `date` 2014-03-03 to 2014-03-14 |

## otc

| table | rows | columns | dates |
|---|---|---|---|
| `endofday` | view | 44 | `closinginsidebidpricedate` 1990-11-19 to 2026-10-20 |

## otc_endofday

| table | rows | columns | dates |
|---|---|---|---|
| `endofday` | 77,794,656 | 44 | `closinginsidebidpricedate`, not asked (too big) |

## panjiva_samp

| table | rows | columns | dates |
|---|---|---|---|
| `boexport` | 3,392 | 40 | `shpmtdate` 2014-01-03 to 2018-09-29 |
| `boimport` | 119,365 | 40 | `shpmtdate` 2014-01-02 to 2018-08-31 |
| `usexport` | 448,164 | 37 | `shpmtdate` 2009-04-01 to 2026-02-26 |
| `usimport` | 2,284,235 | 55 | `arrivaldate` 2007-01-02 to 2026-03-19 |

## phlx

| table | rows | columns | dates |
|---|---|---|---|
| `coph` | view | 22 | `date` 1983-02-28 to 1997-12-19 |
| `iv` | view | 15 | `qdate` 1995-02-06 to 1998-01-28 |

## phlx_all

| table | rows | columns | dates |
|---|---|---|---|
| `coph` | 450,203 | 22 | `date` 1983-02-28 to 1997-12-19 |
| `iv` | 42,674 | 15 | `qdate` 1995-02-06 to 1998-01-28 |

## pitchsmp

| table | rows | columns | dates |
|---|---|---|---|
| `company` | 100 | 100 | `companyfinancingstatusdate` 2012-04-02 to 2026-07-30 |
| `companyaffiliaterelation` | 100 | 13 | `lastupdated` 2025-09-26 to 2026-07-22 |
| `companyboardteamrelation` | 100 | 14 | `startdate` 1974-01-01 to 2025-11-01 |
| `companybuysiderelation` | 100 | 13 | `dealdate` 1995-12-31 to 2026-03-31 |
| `companycikcoderelation` | 100 | 4 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `companyclinicaltrialsrelation` | 100 | 25 | `updateddate` 2010-04-16 to 2026-07-24 |
| `companycompetitorrelation` | 100 | 11 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `companyemployeehistoryrelation` | 100 | 5 | `date` 1989-12-31 to 2026-03-31 |
| `companyentitytyperelation` | 100 | 5 | `lastupdated` 2025-09-26 to 2026-06-17 |
| `companyfinancialrelation` | 100 | 12 | `periodenddate` 1979-12-31 to 2026-03-31 |
| `companyindustryrelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `companyinvestorrelation` | 100 | 12 | `investorsince` 1969-01-01 to 2025-12-29 |
| `companyinvleadpartnerrelation` | 100 | 10 | `dealdate` 1998-09-04 to 2025-12-29 |
| `companylocationrelation` | 100 | 14 | `lastupdated` 2025-09-26 to 2026-07-29 |
| `companymarketanalysisrelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-07-15 |
| `companymorningstarcoderelation` | 100 | 5 | `lastupdated` 2025-09-26 to 2026-07-29 |
| `companynaicscoderelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-07-29 |
| `companynewsrelation` | 100 | 8 | `publishdate` 2026-07-29 to 2026-08-05 |
| `companyserviceproviderrelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `companysiccoderelation` | 100 | 5 | `lastupdated` 2025-09-26 to 2026-06-24 |
| `companysimilarrelation` | 100 | 23 | `lastupdated` 2026-03-11 to 2026-08-05 |
| `companystockexchangerelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-07-15 |
| `companyverticalrelation` | 100 | 4 | `lastupdated` 2025-09-26 to 2025-12-31 |
| `deal` | 100 | 86 | `dealdate` 1996-12-01 to 2025-06-18 |
| `dealbondrelation` | 100 | 47 | `tradedate` 2004-02-20 to 2024-11-14 |
| `dealdebtlenderrelation` | 100 | 49 | `maturitydate` 2012-01-01 to 2027-04-15 |
| `dealdistribbeneficiaryrelation` | 100 | 15 | `lastupdated` 2025-09-26 to 2026-07-01 |
| `dealloanrelation` | 100 | 62 | `closedate` 2004-02-20 to 2024-11-15 |
| `dealserviceproviderrelation` | 100 | 15 | `dealdate` 2004-02-20 to 2024-01-30 |
| `fund` | 100 | 47 | `closedate` 1994-01-01 to 2011-07-05 |
| `fundclosehistoryrelation` | 100 | 6 | `fundclosedate` 1994-01-01 to 2011-07-05 |
| `fundfamilyrelation` | 100 | 5 | `lastupdated` 2026-06-24 to 2026-06-24 |
| `fundinvestorrelation` | 100 | 6 | `lastupdated` 2025-09-26 to 2026-07-01 |
| `fundlpcommitmentrelation` | 100 | 12 | `commitmentdate` 2000-01-05 to 2012-06-29 |
| `fundportfolioholdingsrelation` | 100 | 37 | `maturity` 2024-11-25 to 2033-07-31 |
| `fundreturnrelation` | 100 | 27 | `lastupdated` 2025-10-30 to 2026-07-22 |
| `fundserviceproviderrelation` | 100 | 10 | `lastupdated` 2025-09-26 to 2026-07-22 |
| `fundteamrelation` | 100 | 11 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `investor` | 100 | 130 | `investmentprofessionalcountdate` 2012-03-30 to 2026-08-01 |
| `investoraffiliaterelation` | 100 | 12 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `investorboardteamrelation` | 100 | 14 | `startdate` 1991-05-01 to 2025-12-01 |
| `investorcoinvestorrelation` | 100 | 6 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `investorentitytyperelation` | 100 | 5 | `lastupdated` 2025-09-26 to 2026-04-08 |
| `investorfundrelation` | 100 | 5 | `lastupdated` 2025-09-26 to 2025-09-26 |
| `investorinvestdealrelation` | 100 | 7 | `lastinvestment` 2000-01-26 to 2026-08-04 |
| `investorinvestindustrycoderel` | 100 | 10 | `lastinvestment` 2005-05-25 to 2026-08-04 |
| `investorinvestyearrelation` | 100 | 7 | `lastinvestment` 1988-12-01 to 2026-08-04 |
| `investorlimitedpartnerrelation` | 100 | 11 | `lastcommitmentdate` 1993-01-01 to 2026-06-29 |
| `investorlocationrelation` | 100 | 14 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `investornewsrelation` | 100 | 8 | `publishdate` 2026-07-29 to 2026-08-05 |
| `investorserviceproviderrelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `investortyperelation` | 100 | 5 | `lastupdated` 2025-09-26 to 2026-07-22 |
| `limitedpartner` | 100 | 99 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `lpboardteamrelation` | 100 | 15 | `startdate` 1886-01-01 to 2024-08-01 |
| `lpfundcommitmentrelation` | 100 | 7 | `commitmentdate` 1996-01-01 to 2021-05-28 |
| `lpmandaterelation` | 100 | 12 | `announceddate` 2010-09-21 to 2026-02-27 |
| `lpserviceproviderrelation` | 100 | 8 | `lastupdated` 2025-09-26 to 2026-07-22 |
| `person` | 100 | 33 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `personadvisoryrelation` | 100 | 11 | `startdate` 2006-09-01 to 2021-01-01 |
| `personaffiliateddealrelation` | 100 | 9 | `dealdate` 1994-08-01 to 2026-07-06 |
| `personaffiliatedfundrelation` | 100 | 7 | `lastupdated` 2026-08-05 to 2026-08-05 |
| `personboardseatrelation` | 100 | 12 | `startdate` 1975-04-04 to 2024-01-01 |
| `personeducationrelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-06-24 |
| `personpositionrelation` | 100 | 13 | `startdate` 1968-01-01 to 2024-10-01 |
| `serviceprovider` | 100 | 32 | `lastupdated` 2025-09-26 to 2026-08-05 |
| `serviceproviderboardteamrelation` | 100 | 15 | `startdate` 1987-01-01 to 2026-01-01 |
| `serviceprovidercompanyrelation` | 100 | 7 | `lastupdated` 2025-09-26 to 2026-07-08 |
| `serviceprovidercompdealrelation` | 100 | 10 | `dealdate` 1999-11-18 to 2026-06-15 |
| `serviceproviderinvfundrelation` | 100 | 8 | `lastupdated` 2025-09-26 to 2026-07-01 |
| `serviceproviderlprelation` | 100 | 6 | `lastupdated` 2025-09-26 to 2026-06-03 |
| `wrds_fund_returns` | 100 | 29 | `fundretrellastupdated` 2025-10-30 to 2026-07-22 |

## pnjvasmp

| table | rows | columns | dates |
|---|---|---|---|
| `boexport` | view | 40 | `shpmtdate` 2014-01-03 to 2018-09-29 |
| `boimport` | view | 40 | `shpmtdate` 2014-01-02 to 2018-08-31 |
| `usexport` | view | 37 | `shpmtdate` 2009-04-01 to 2026-02-26 |
| `usimport` | view | 55 | `arrivaldate` 2007-01-02 to 2026-03-19 |

## preqsamp

| table | rows | columns | dates |
|---|---|---|---|
| `benchmarks` | view | 53 | `qdate` 2000-12-31 to 2019-03-31 |
| `buyoutdealsdetails` | view | 41 | `deal_date` 1991-06-01 to 2019-06-12 |
| `cashflow` | view | 8 | `transaction_date` 2015-01-14 to 2015-04-01 |
| `funddetails` | view | 31 | `fundraising_launch_date` 2006-12-31 to 2015-05-01 |
| `fundhistoricperformance` | view | 9 | `date_reported` 2008-06-30 to 2011-12-31 |
| `fundterms` | view | 20 | - |
| `investordetails` | view | 45 | - |
| `investorportfolio` | view | 5 | - |
| `managerdetails` | view | 35 | `lastupdated` 2011-06-07 to 2019-08-02 |
| `managerinvestmenttypes` | view | 33 | - |
| `venturedealsdetails` | view | 25 | `deal_date` 2002-10-01 to 2019-06-25 |

## preqsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `benchmarks` | 72,260 | 53 | `qdate` 2000-12-31 to 2019-03-31 |
| `buyoutdealsdetails` | 100 | 41 | `deal_date` 1991-06-01 to 2019-06-12 |
| `cashflow` | 99 | 8 | `transaction_date` 2015-01-14 to 2015-04-01 |
| `funddetails` | 118 | 31 | `fundraising_launch_date` 2006-12-31 to 2015-05-01 |
| `fundhistoricperformance` | 102 | 9 | `date_reported` 2008-06-30 to 2011-12-31 |
| `fundterms` | 100 | 20 | - |
| `investordetails` | 100 | 45 | - |
| `investorportfolio` | 105 | 5 | - |
| `managerdetails` | 100 | 35 | `lastupdated` 2011-06-07 to 2019-08-02 |
| `managerinvestmenttypes` | 113 | 33 | - |
| `venturedealsdetails` | 100 | 25 | `deal_date` 2002-10-01 to 2019-06-25 |

## public

| table | rows | columns | dates |
|---|---|---|---|
| `exp_per_event_table1` | view | 8 | - |
| `exp_per_event_table2` | view | 8 | - |
| `meps_exp_per_event_table1` | view | 9 | - |
| `meps_exp_per_event_table2` | view | 9 | - |
| `meps_top_prescribed` | view | 9 | - |
| `meps_top_therapeutic_classes` | view | 9 | - |
| `mepsins` | view | 24 | - |
| `mepssumm` | view | 85 | - |
| `mepssummexp_per_condition` | view | 29 | - |
| `pg_stat_statements` | view | 49 | `stats_since` 2026-10-03 to 2026-11-19 |
| `pg_stat_statements_info` | view | 2 | `stats_reset` 2026-10-03 to 2026-10-03 |
| `top_prescribed` | view | 8 | - |
| `top_therapeutic_classes` | view | 8 | - |

## public_all

| table | rows | columns | dates |
|---|---|---|---|
| `exp_per_event_table1` | 30 | 8 | - |
| `exp_per_event_table2` | 25 | 8 | - |
| `meps_exp_per_event_table1` | 30 | 9 | - |
| `meps_exp_per_event_table2` | 25 | 9 | - |
| `meps_top_prescribed` | 331 | 9 | - |
| `meps_top_therapeutic_classes` | 94 | 9 | - |
| `mepsins` | 144 | 24 | - |
| `mepssumm` | 601 | 85 | - |
| `mepssummexp_per_condition` | 921 | 29 | - |
| `top_prescribed` | 331 | 8 | - |
| `top_therapeutic_classes` | 94 | 8 | - |

## pwt

| table | rows | columns | dates |
|---|---|---|---|
| `na` | view | 14 | - |
| `na70` | view | 22 | - |
| `pwt61` | view | 25 | - |
| `pwt62` | view | 27 | - |
| `pwt63` | view | 36 | - |
| `pwt70` | view | 37 | - |
| `pwt71` | view | 37 | - |

## pwt_all

| table | rows | columns | dates |
|---|---|---|---|
| `na` | 10,863 | 14 | - |
| `na70` | 12,660 | 22 | - |
| `pwt61` | 10,208 | 25 | - |
| `pwt62` | 10,340 | 27 | - |
| `pwt63` | 11,020 | 36 | - |
| `pwt70` | 11,400 | 37 | - |
| `pwt71` | 11,590 | 37 | - |

## ravenpack_trial

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 55 | `rpa_date_utc`, not asked |
| `rpa_entity_mappings` | 437,845 | 6 | `range_start` 1582-01-11 to 2020-12-31 |
| `rpa_full_equities` | 409,198 | 52 | `rpa_date_utc` 2020-09-30 to 2020-09-30 |
| `rpa_full_global_macro` | 1,773,572 | 52 | `rpa_date_utc` 2020-09-30 to 2020-09-30 |
| `rpa_source_list` | 21,234 | 6 | `range_start` 2000-01-01 to 2020-09-20 |
| `rpa_taxonomy` | 6,895 | 10 | - |
| `wrds_rpa_all_mappings` | 72,217 | 6 | - |
| `wrds_rpa_company_names` | 316,157 | 4 | - |

## reprisk_sample

| table | rows | columns | dates |
|---|---|---|---|
| `pm_company_identifiers` | 3 | 9 | - |
| `pm_issue_data` | 124 | 10 | `date` 2010-01-31 to 2010-12-31 |
| `pm_location_data` | 45 | 10 | `date` 2010-01-31 to 2010-12-31 |
| `pm_news_data` | 69 | 13 | `news_date` 2010-01-07 to 2010-12-28 |
| `pm_rri_data` | 36 | 11 | `date` 2010-01-31 to 2010-12-31 |
| `pm_tag_data` | 11 | 10 | `date` 2010-03-31 to 2010-12-31 |
| `reprisk_company_lookup` | 151 | 3 | - |
| `v2_company_identifiers` | 15 | 9 | - |
| `v2_metrics` | 465 | 18 | `date` 2021-01-01 to 2021-01-31 |
| `v2_risk_incidents` | 177 | 125 | `incident_date` 2021-01-01 to 2021-01-31 |
| `v2_wrds_company_lookup` | 1,517 | 3 | - |

## repsamp

| table | rows | columns | dates |
|---|---|---|---|
| `pm_company_identifiers` | view | 9 | - |
| `pm_issue_data` | view | 10 | `date` 2010-01-31 to 2010-12-31 |
| `pm_location_data` | view | 10 | `date` 2010-01-31 to 2010-12-31 |
| `pm_news_data` | view | 13 | `news_date` 2010-01-07 to 2010-12-28 |
| `pm_rri_data` | view | 11 | `date` 2010-01-31 to 2010-12-31 |
| `pm_tag_data` | view | 10 | `date` 2010-03-31 to 2010-12-31 |
| `reprisk_company_lookup` | view | 3 | - |
| `v2_company_identifiers` | view | 9 | - |
| `v2_metrics` | view | 18 | `date` 2021-01-01 to 2021-01-31 |
| `v2_risk_incidents` | view | 125 | `incident_date` 2021-01-01 to 2021-01-31 |
| `v2_wrds_company_lookup` | view | 3 | - |

## revelio_samp

| table | rows | columns | dates |
|---|---|---|---|
| `company_mapping` | 3 | 34 | - |
| `individual_positions` | 1,991,185 | 24 | `startdate` 1950-01-01 to 2026-05-01 |
| `individual_positions_raw` | 1,991,185 | 6 | - |
| `individual_role_lookup` | 1,499 | 7 | - |
| `individual_role_lookup_v3` | 17,000 | 11 | - |
| `individual_user` | 1,300,745 | 19 | `updated_dt` 2016-10-01 to 2026-05-05 |
| `individual_user_education` | 2,372,560 | 10 | `startdate` 1900-01-01 to 2031-01-01 |
| `individual_user_education_raw` | 2,372,560 | 6 | - |
| `individual_user_raw` | 1,300,745 | 3 | - |
| `individual_user_skill_lookup` | 31,288 | 8 | - |
| `individual_user_skills` | 47,899,684 | 6 | `first_reported`, not asked (too big) |
| `layoffs` | 32 | 20 | `notice_date` 2007-02-28 to 2026-04-23 |
| `postings_cosmos` | 1,076,187 | 28 | `post_date` 2008-06-13 to 2026-05-08 |
| `postings_cosmos_raw` | 10,000 | 5 | - |
| `postings_role_lookup_v3` | 17,001 | 11 | - |
| `regions` | 247 | 2 | - |
| `school_mapping` | 56,458 | 16 | - |
| `sentiment_individual_reviews` | 96,797 | 38 | `review_date` 2008-01-31 to 2026-05-05 |
| `sentiment_role_lookup` | 16,147 | 12 | - |
| `sentiment_scores` | 3 | 16 | - |
| `workforce_dynamics_geo` | 25,013,120 | 25 | `datemonth`, not asked (too big) |

## revsamp

| table | rows | columns | dates |
|---|---|---|---|
| `company_mapping` | view | 34 | - |
| `individual_positions` | view | 24 | `startdate` 1950-01-01 to 2026-05-01 |
| `individual_positions_raw` | view | 6 | - |
| `individual_role_lookup` | view | 7 | - |
| `individual_role_lookup_v3` | view | 11 | - |
| `individual_user` | view | 19 | `updated_dt` 2016-10-01 to 2026-05-05 |
| `individual_user_education` | view | 10 | `startdate` 1900-01-01 to 2031-01-01 |
| `individual_user_education_raw` | view | 6 | - |
| `individual_user_raw` | view | 3 | - |
| `individual_user_skill_lookup` | view | 8 | - |
| `individual_user_skills` | view | 6 | `first_reported` 2012-12-11 to 2026-04-30 |
| `layoffs` | view | 20 | `notice_date` 2007-02-28 to 2026-04-23 |
| `postings_cosmos` | view | 28 | `post_date` 2008-06-13 to 2026-05-08 |
| `postings_cosmos_raw` | view | 5 | - |
| `postings_role_lookup_v3` | view | 11 | - |
| `regions` | view | 2 | - |
| `school_mapping` | view | 16 | - |
| `sentiment_individual_reviews` | view | 38 | `review_date` 2008-01-31 to 2026-05-05 |
| `sentiment_role_lookup` | view | 12 | - |
| `sentiment_scores` | view | 16 | - |
| `workforce_dynamics_geo` | view | 25 | `datemonth` 2008-01-01 to 2026-04-01 |

## risk

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_glob` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_mf` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_pro` | view (empty) | 76 | `meetingdate`, not asked |
| `chars_props` | view (empty) | 28 | `meeting_date`, not asked |
| `chars_us` | view (empty) | 76 | `meetingdate`, not asked |
| `committee96_97` | view | 11 | - |
| `committee_numbers_97` | view | 15 | - |
| `directors` | view | 79 | `meetingdate` 1993-04-16 to 2006-12-15 |
| `dirnames` | view | 4 | - |
| `globalvoteresults` | view | 41 | `meetingdate` 2013-01-02 to 2025-12-31 |
| `mf_company_names` | view | 2 | - |
| `mf_institution_names` | view | 2 | - |
| `proposals` | view | 28 | `meeting_date` 2006-01-01 to 2025-12-16 |
| `proposals_legacy` | view | 22 | `mtg_date` 1997-01-14 to 2019-12-31 |
| `rmdirectors` | view | 62 | `meetingdate` 2007-01-02 to 2025-07-15 |
| `va_proposals` | view | 28 | `meeting_date` 2006-01-01 to 2025-12-29 |
| `vavoteresults` | view | 29 | `recorddate` 2002-02-26 to 2025-12-21 |
| `voteanalysis_npx` | view | 30 | `meetingdate` 2003-07-01 to 2025-06-30 |
| `votes` | view | 20 | `meeting_date` 1997-01-08 to 2006-11-02 |

## risk_directors

| table | rows | columns | dates |
|---|---|---|---|
| `committee96_97` | 30,498 | 11 | - |
| `committee_numbers_97` | 1,382 | 15 | - |
| `directors` | 166,375 | 79 | `meetingdate` 1993-04-16 to 2006-12-15 |
| `dirnames` | 19,551 | 4 | - |
| `rmdirectors` | 268,451 | 62 | `meetingdate` 2007-01-02 to 2025-07-15 |

## risk_proposals

| table | rows | columns | dates |
|---|---|---|---|
| `chars_props` | view (empty) | 28 | `meeting_date`, not asked |
| `proposals` | 17,292 | 28 | `meeting_date` 2006-01-01 to 2025-12-16 |
| `proposals_legacy` | 22,122 | 22 | `mtg_date` 1997-01-14 to 2019-12-31 |

## risk_votes

| table | rows | columns | dates |
|---|---|---|---|
| `votes` | 21,042 | 20 | `meeting_date` 1997-01-08 to 2006-11-02 |

## risksamp

| table | rows | columns | dates |
|---|---|---|---|
| `beneown` | view | 8 | - |
| `bhown` | view | 6 | - |
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `companyfy` | view | 19 | `fiscalyearend` 1998-12-31 to 2016-09-30 |
| `comppeer` | view | 6 | - |
| `consultant` | view | 11 | - |
| `dircomp` | view | 11 | - |
| `exervest` | view | 8 | - |
| `globalvoteresults` | view | 41 | `meetingdate` 2013-01-18 to 2024-12-03 |
| `gpbaabs` | view | 32 | - |
| `gpbaacc` | view | 41 | - |
| `gpbaaccpeer` | view | 5 | - |
| `gpbagrant` | view | 33 | `grantdate` 1998-01-04 to 9999-01-01 |
| `gpbarel` | view | 29 | - |
| `gpbarelpeer` | view | 5 | - |
| `holdingreq` | view | 19 | - |
| `oeoption` | view | 10 | `expirationdate` 2008-02-09 to 2025-07-05 |
| `oestock` | view | 9 | - |
| `participantfy` | view | 20 | - |
| `proposals` | view | 21 | `mtg_date` 1997-02-11 to 2012-11-15 |
| `rmdirectors` | view | 62 | `meetingdate` 2007-01-11 to 2012-11-15 |
| `rmgovernance` | view | 34 | `meetingdate` 2007-01-25 to 2022-06-23 |
| `sumcomp` | view | 15 | - |
| `va_proposals` | view | 28 | `meeting_date` 2006-04-19 to 2025-11-05 |
| `vavoteresults` | view | 29 | `recorddate` 2002-11-29 to 2024-11-01 |
| `voteanalysis_npx` | view | 21 | `meetingdate` 2003-07-18 to 2015-06-25 |
| `votes` | view | 20 | `meeting_date` 1997-01-30 to 2006-09-18 |

## risksamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `beneown` | 100 | 8 | - |
| `bhown` | 100 | 6 | - |
| `chars` | view (empty) | 76 | `meetingdate`, not asked |
| `companyfy` | 100 | 19 | `fiscalyearend` 1998-12-31 to 2016-09-30 |
| `comppeer` | 100 | 6 | - |
| `consultant` | 100 | 11 | - |
| `dircomp` | 100 | 11 | - |
| `exervest` | 100 | 8 | - |
| `globalvoteresults` | 6,481 | 41 | `meetingdate` 2013-01-18 to 2024-12-03 |
| `gpbaabs` | 100 | 32 | - |
| `gpbaacc` | 100 | 41 | - |
| `gpbaaccpeer` | 100 | 5 | - |
| `gpbagrant` | 100 | 33 | `grantdate` 1998-01-04 to 9999-01-01 |
| `gpbarel` | 100 | 29 | - |
| `gpbarelpeer` | 100 | 5 | - |
| `holdingreq` | 100 | 19 | - |
| `oeoption` | 100 | 10 | `expirationdate` 2008-02-09 to 2025-07-05 |
| `oestock` | 100 | 9 | - |
| `participantfy` | 100 | 20 | - |
| `proposals` | 870 | 21 | `mtg_date` 1997-02-11 to 2012-11-15 |
| `rmdirectors` | 4,980 | 62 | `meetingdate` 2007-01-11 to 2012-11-15 |
| `rmgovernance` | 1,742 | 34 | `meetingdate` 2007-01-25 to 2022-06-23 |
| `sumcomp` | 100 | 15 | - |
| `va_proposals` | 1,003 | 28 | `meeting_date` 2006-04-19 to 2025-11-05 |
| `vavoteresults` | 6,972 | 29 | `recorddate` 2002-11-29 to 2024-11-01 |
| `voteanalysis_npx` | 9,484 | 21 | `meetingdate` 2003-07-18 to 2015-06-25 |
| `votes` | 855 | 20 | `meeting_date` 1997-01-30 to 2006-09-18 |

## rpnasamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 55 | `rpa_date_utc`, not asked |
| `rpa_entity_mappings` | view | 6 | `range_start` 1582-01-11 to 2020-12-31 |
| `rpa_full_equities` | view | 52 | `rpa_date_utc` 2020-09-30 to 2020-09-30 |
| `rpa_full_global_macro` | view | 52 | `rpa_date_utc` 2020-09-30 to 2020-09-30 |
| `rpa_source_list` | view | 6 | `range_start` 2000-01-01 to 2020-09-20 |
| `rpa_taxonomy` | view | 10 | - |
| `wrds_rpa_all_mappings` | view | 6 | - |
| `wrds_rpa_company_names` | view | 4 | - |

## rq_all

| table | rows | columns | dates |
|---|---|---|---|
| `rq_data` | 52,779 | 8 | - |

## rstat_samp

| table | rows | columns | dates |
|---|---|---|---|
| `royalties` | 13 | 36 | `royaltystat_activate_date` 2003-05-02 to 2021-03-23 |

## rstatsmp

| table | rows | columns | dates |
|---|---|---|---|
| `royalties` | view | 36 | `royaltystat_activate_date` 2003-05-02 to 2021-03-23 |

## sdcsamp

| table | rows | columns | dates |
|---|---|---|---|
| `calldata` | view | 12 | `cldat1` 2023-04-03 to 2043-07-01 |
| `deals_data` | view | 64 | `wrds_first_sale_date` 2022-01-12 to 2024-02-12 |
| `ma_advisors` | view | 22 | `dateann` 2016-03-13 to 2016-03-19 |
| `ma_details` | view | 168 | `dateann` 2016-03-13 to 2016-03-19 |
| `ma_events` | view | 10 | `dateann` 2016-03-13 to 2016-03-19 |
| `maturity` | view | 7 | `endserialmaty` 2025-07-01 to 2057-06-15 |
| `ni_details` | view | 158 | `master_deal_date` 2016-03-14 to 2016-03-19 |
| `ratings` | view | 8 | - |
| `sdc_joint_ventures` | view | 125 | `aa_hdate` 2018-11-26 to 2038-12-31 |
| `wrds_bo_fund_firm` | view | 51 | `founded_fund` 1960-01-01 to 2022-01-01 |
| `wrds_bo_fundra_fund` | view | 34 | `report_date` 1992-03-31 to 2022-09-30 |
| `wrds_bo_invdtl_compn_fund` | view | 92 | `round_date` 2023-01-01 to 2024-01-25 |
| `wrds_managers` | view | 5 | - |
| `wrds_vc_fund_firm` | view | 51 | `founded_fund` 1972-01-01 to 2022-01-01 |
| `wrds_vc_fundra_fund` | view | 34 | `report_date` 1972-12-31 to 2022-06-30 |
| `wrds_vc_invdtl_compn_fund` | view | 92 | `round_date` 2023-01-04 to 2024-01-30 |

## secsamp

| table | rows | columns | dates |
|---|---|---|---|
| `_qvards_` | view (empty) | 79 | `fdate`, not asked |
| `bow_2022` | view | 3 | - |
| `bow_cossim` | view | 27 | `fdate` 2022-01-06 to 2022-12-29 |
| `bow_filingsummary` | view | 18 | `fdate` 2022-01-03 to 2022-12-30 |
| `bow_wordsummary` | view | 25 | - |
| `cisdf` | view | 13 | `start_file_date` 1967-02-09 to 1989-03-26 |
| `exhibits` | view | 17 | `fdate` 2023-01-03 to 2023-12-29 |
| `forms` | view | 10 | `fdate` 2023-01-03 to 2023-12-29 |
| `items8k` | view | 15 | `fdate` 2023-01-04 to 2023-12-29 |
| `sample_ciks` | view | 2 | - |
| `wciklink_cusip` | view | 11 | `cikdate1` 1994-01-18 to 2026-08-03 |
| `wciklink_gvkey` | view | 25 | `sec_start_date` 1994-01-05 to 2003-02-27 |
| `wciklink_names` | view | 17 | `first_cik_date` 1994-01-05 to 2003-02-27 |
| `wciklink_ticker` | view | 6 | `ftdate` 2003-05-05 to 2024-08-19 |
| `wrds_13f_holdings` | view | 18 | `rdate` 2021-09-30 to 2023-09-30 |
| `wrds_13f_link` | view | 6 | - |
| `wrds_13f_summary` | view | 23 | `rdate` 2021-09-30 to 2023-09-30 |
| `wrds_forms` | view | 17 | `fdate` 2023-01-03 to 2023-12-29 |
| `wrds_forms_reg` | view | 19 | `fdate` 2023-01-03 to 2023-12-29 |
| `wrds_nlpsa` | view | 43 | `fdate` 2023-01-03 to 2023-12-29 |

## secsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `_qvards_` | view (empty) | 79 | `fdate`, not asked |
| `bow_2022` | 3,186,708 | 3 | - |
| `bow_cossim` | 10,593 | 27 | `fdate` 2022-01-06 to 2022-12-29 |
| `bow_filingsummary` | 4,763 | 18 | `fdate` 2022-01-03 to 2022-12-30 |
| `bow_wordsummary` | 164,301 | 25 | - |
| `cisdf` | 229 | 13 | `start_file_date` 1967-02-09 to 1989-03-26 |
| `exhibits` | 46,681 | 17 | `fdate` 2023-01-03 to 2023-12-29 |
| `forms` | 4,883 | 10 | `fdate` 2023-01-03 to 2023-12-29 |
| `items8k` | 1,417 | 15 | `fdate` 2023-01-04 to 2023-12-29 |
| `sample_ciks` | view | 2 | - |
| `wciklink_cusip` | 334 | 11 | `cikdate1` 1994-01-18 to 2026-08-03 |
| `wciklink_gvkey` | 320 | 25 | `sec_start_date` 1994-01-05 to 2003-02-27 |
| `wciklink_names` | 348 | 17 | `first_cik_date` 1994-01-05 to 2003-02-27 |
| `wciklink_ticker` | 93 | 6 | `ftdate` 2003-05-05 to 2024-08-19 |
| `wrds_13f_holdings` | 18,163 | 18 | `rdate` 2021-09-30 to 2023-09-30 |
| `wrds_13f_link` | 11 | 6 | - |
| `wrds_13f_summary` | 64 | 23 | `rdate` 2021-09-30 to 2023-09-30 |
| `wrds_forms` | 4,883 | 17 | `fdate` 2023-01-03 to 2023-12-29 |
| `wrds_forms_reg` | 9,795 | 19 | `fdate` 2023-01-03 to 2023-12-29 |
| `wrds_nlpsa` | 4,883 | 43 | `fdate` 2023-01-03 to 2023-12-29 |

## shvlsamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 1 | - |
| `wrds_shortvolume_samp` | view | 46 | `date` 2015-01-02 to 2020-12-31 |

## snapsamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 40 | - |
| `wrds_cs_names` | view | 13 | `begdate` 1986-12-14 to 2015-04-28 |
| `wrds_csa_pit` | view | 579 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csa_pit_sorted` | view | 579 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csa_restated` | view | 579 | `datadate` 1968-12-31 to 2015-03-31 |
| `wrds_csa_unrestated` | view | 579 | `datadate` 1968-12-31 to 2015-03-31 |
| `wrds_csq_pit` | view | 620 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csq_pit_sorted` | view | 620 | `pitdate1` 1986-12-14 to 2015-04-28 |
| `wrds_csq_restated` | view | 620 | `datadate` 1973-09-30 to 2015-03-31 |
| `wrds_csq_unrestated` | view | 620 | `datadate` 1973-09-30 to 2015-03-31 |

## snlsamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 2 | - |
| `wrds_fig_flowperiod_primary` | view | 242 | `periodenddate` 1983-03-31 to 2017-09-30 |
| `wrds_fig_stockperiod_primary` | view (empty) | 174 | `periodEndDate`, not measured (query failed) |
| `wrds_institutions` | view (empty) | 23 | - |

## snlsamp_fig

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 2 | - |
| `wrds_fig_flowperiod_primary` | 41,384 | 242 | `periodenddate` 1983-03-31 to 2017-09-30 |
| `wrds_fig_stockperiod_primary` | view (empty) | 174 | `periodEndDate`, not measured (query failed) |
| `wrds_institutions` | view (empty) | 23 | - |

## sustainalyticssamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 167 | `date`, not asked |
| `esgrr_clusters` | 2,164 | 6 | `fielddate` 2010-01-01 to 2024-10-08 |
| `esgrr_focus` | 18,222 | 6 | `fielddate` 2024-06-13 to 2025-09-12 |
| `esgrr_indicators` | 75,943 | 7 | `fielddate` 2024-06-13 to 2025-09-04 |
| `esgrr_meis` | 68,229 | 6 | `fielddate` 2024-06-13 to 2025-09-10 |
| `hist_raw_score` | 2,281 | 162 | `date` 2009-08-16 to 2016-06-07 |
| `hist_weighted_score` | 2,281 | 167 | `date` 2009-08-16 to 2016-06-07 |
| `hist_weights` | 2,281 | 162 | `date` 2009-08-16 to 2016-06-07 |
| `reference_data` | 99 | 84 | `extractiondate` 2025-08-11 to 2025-08-11 |

## sustsamp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 167 | `date`, not asked |
| `esgrr_clusters` | view | 6 | `fielddate` 2010-01-01 to 2024-10-08 |
| `esgrr_focus` | view | 6 | `fielddate` 2024-06-13 to 2025-09-12 |
| `esgrr_indicators` | view | 7 | `fielddate` 2024-06-13 to 2025-09-04 |
| `esgrr_meis` | view | 6 | `fielddate` 2024-06-13 to 2025-09-10 |
| `hist_raw_score` | view | 162 | `date` 2009-08-16 to 2016-06-07 |
| `hist_weighted_score` | view | 167 | `date` 2009-08-16 to 2016-06-07 |
| `hist_weights` | view | 162 | `date` 2009-08-16 to 2016-06-07 |
| `reference_data` | view | 84 | `extractiondate` 2025-08-11 to 2025-08-11 |

## taqmsamp

| table | rows | columns | dates |
|---|---|---|---|
| `arca_idf_x100_20211004` | view | 12 | - |
| `arca_idf_x100_20211005` | view | 12 | - |
| `arca_idf_x101_20211004` | view | 11 | - |
| `arca_idf_x101_20211005` | view | 11 | - |
| `arca_idf_x102_20211004` | view | 7 | - |
| `arca_idf_x102_20211005` | view | 7 | - |
| `arca_idf_x103_20211004` | view | 12 | - |
| `arca_idf_x103_20211005` | view | 12 | - |
| `arca_idf_x104_20211004` | view | 11 | - |
| `arca_idf_x104_20211005` | view | 11 | - |
| `arca_idf_x105_20211004` | view | 21 | - |
| `arca_idf_x105_20211005` | view | 21 | - |
| `arca_idf_x110_20211004` | view | 10 | - |
| `arca_idf_x110_20211005` | view | 10 | - |
| `arca_idf_x111_20211004` | view | 9 | - |
| `arca_idf_x111_20211005` | view | 9 | - |
| `arca_idf_x112_20211004` | view (empty) | 6 | - |
| `arca_idf_x112_20211005` | view (empty) | 6 | - |
| `arca_idf_x113_20211004` | view (empty) | 7 | - |
| `arca_idf_x113_20211005` | view (empty) | 7 | - |
| `arca_idf_x114_20211004` | view | 6 | - |
| `arca_idf_x114_20211005` | view | 6 | - |
| `arca_idf_x34_20211004` | view | 14 | - |
| `arca_idf_x34_20211005` | view | 14 | - |
| `arca_idf_x3_20211004` | view | 16 | - |
| `arca_idf_x3_20211005` | view | 16 | - |
| `cqm_20090213` | view | 17 | `date` 2009-02-13 to 2009-02-13 |
| `ctm_20090213` | view | 13 | `date` 2009-02-13 to 2009-02-13 |
| `ix_cqm_20090213` | view | 4 | - |
| `ix_ctm_20090213` | view | 4 | - |
| `ix_nbbom_20090213` | view | 4 | - |
| `nbbom_20090213` | view | 31 | `date` 2009-02-13 to 2009-02-13 |
| `nyse_idf_x100_20211004` | view | 12 | - |
| `nyse_idf_x100_20211005` | view | 12 | - |
| `nyse_idf_x101_20211004` | view | 11 | - |
| `nyse_idf_x101_20211005` | view | 11 | - |
| `nyse_idf_x102_20211004` | view | 7 | - |
| `nyse_idf_x102_20211005` | view | 7 | - |
| `nyse_idf_x103_20211004` | view | 12 | - |
| `nyse_idf_x103_20211005` | view | 12 | - |
| `nyse_idf_x104_20211004` | view | 11 | - |
| `nyse_idf_x104_20211005` | view | 11 | - |
| `nyse_idf_x105_20211004` | view | 21 | - |
| `nyse_idf_x105_20211005` | view | 21 | - |
| `nyse_idf_x110_20211004` | view | 10 | - |
| `nyse_idf_x110_20211005` | view | 10 | - |
| `nyse_idf_x111_20211004` | view | 9 | - |
| `nyse_idf_x111_20211005` | view | 9 | - |
| `nyse_idf_x112_20211004` | view (empty) | 6 | - |
| `nyse_idf_x112_20211005` | view (empty) | 6 | - |
| `nyse_idf_x113_20211004` | view (empty) | 7 | - |
| `nyse_idf_x113_20211005` | view (empty) | 7 | - |
| `nyse_idf_x114_20211004` | view | 6 | - |
| `nyse_idf_x114_20211005` | view | 6 | - |
| `nyse_idf_x34_20211004` | view | 14 | - |
| `nyse_idf_x34_20211005` | view | 14 | - |
| `nyse_idf_x3_20211004` | view | 16 | - |
| `nyse_idf_x3_20211005` | view | 16 | - |

## taqmsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `arca_idf_x100_20211004` | 177,965,952 | 12 | - |
| `arca_idf_x100_20211005` | 117,173,368 | 12 | - |
| `arca_idf_x101_20211004` | 12,729,434 | 11 | - |
| `arca_idf_x101_20211005` | 8,553,090 | 11 | - |
| `arca_idf_x102_20211004` | 175,030,880 | 7 | - |
| `arca_idf_x102_20211005` | 114,739,600 | 7 | - |
| `arca_idf_x103_20211004` | 3,653,512 | 12 | - |
| `arca_idf_x103_20211005` | 2,899,964 | 12 | - |
| `arca_idf_x104_20211004` | 36,281,240 | 11 | - |
| `arca_idf_x104_20211005` | 23,633,336 | 11 | - |
| `arca_idf_x105_20211004` | 3,616,432 | 21 | - |
| `arca_idf_x105_20211005` | 2,879,470 | 21 | - |
| `arca_idf_x110_20211004` | 692,009 | 10 | - |
| `arca_idf_x110_20211005` | 604,592 | 10 | - |
| `arca_idf_x111_20211004` | 3,276 | 9 | - |
| `arca_idf_x111_20211005` | 3,062 | 9 | - |
| `arca_idf_x112_20211004` | view (empty) | 6 | - |
| `arca_idf_x112_20211005` | view (empty) | 6 | - |
| `arca_idf_x113_20211004` | view (empty) | 7 | - |
| `arca_idf_x113_20211005` | view (empty) | 7 | - |
| `arca_idf_x114_20211004` | 45,348,760 | 6 | - |
| `arca_idf_x114_20211005` | 39,034,960 | 6 | - |
| `arca_idf_x34_20211004` | 31,197 | 14 | - |
| `arca_idf_x34_20211005` | 31,217 | 14 | - |
| `arca_idf_x3_20211004` | 6,202 | 16 | - |
| `arca_idf_x3_20211005` | 6,201 | 16 | - |
| `cqm_20090213` | 524,966,304 | 17 | `date`, not asked (too big) |
| `ctm_20090213` | 35,386,928 | 13 | `date`, not asked (too big) |
| `ix_cqm_20090213` | 8,203 | 4 | - |
| `ix_ctm_20090213` | 7,611 | 4 | - |
| `ix_nbbom_20090213` | 8,168 | 4 | - |
| `nbbom_20090213` | 161,567,648 | 31 | `date`, not asked (too big) |
| `nyse_idf_x100_20211004` | 170,515,072 | 12 | - |
| `nyse_idf_x100_20211005` | 119,334,456 | 12 | - |
| `nyse_idf_x101_20211004` | 8,344,516 | 11 | - |
| `nyse_idf_x101_20211005` | 6,066,882 | 11 | - |
| `nyse_idf_x102_20211004` | 162,986,768 | 7 | - |
| `nyse_idf_x102_20211005` | 112,567,928 | 7 | - |
| `nyse_idf_x103_20211004` | 6,516,350 | 12 | - |
| `nyse_idf_x103_20211005` | 5,412,733 | 12 | - |
| `nyse_idf_x104_20211004` | 12,352,722 | 11 | - |
| `nyse_idf_x104_20211005` | 9,363,753 | 11 | - |
| `nyse_idf_x105_20211004` | 583,635 | 21 | - |
| `nyse_idf_x105_20211005` | 513,805 | 21 | - |
| `nyse_idf_x110_20211004` | 1,471,125 | 10 | - |
| `nyse_idf_x110_20211005` | 1,277,304 | 10 | - |
| `nyse_idf_x111_20211004` | 5,984 | 9 | - |
| `nyse_idf_x111_20211005` | 5,881 | 9 | - |
| `nyse_idf_x112_20211004` | view (empty) | 6 | - |
| `nyse_idf_x112_20211005` | view (empty) | 6 | - |
| `nyse_idf_x113_20211004` | view (empty) | 7 | - |
| `nyse_idf_x113_20211005` | view (empty) | 7 | - |
| `nyse_idf_x114_20211004` | 42,748,236 | 6 | - |
| `nyse_idf_x114_20211005` | 56,068,768 | 6 | - |
| `nyse_idf_x34_20211004` | 47,044 | 14 | - |
| `nyse_idf_x34_20211005` | 46,973 | 14 | - |
| `nyse_idf_x3_20211004` | 11,273 | 16 | - |
| `nyse_idf_x3_20211005` | 11,279 | 16 | - |

## taqsamp

| table | rows | columns | dates |
|---|---|---|---|
| `cq0002` | view (empty) | 11 | `date`, not asked |
| `cq_20080107` | view | 10 | `date` 2008-01-07 to 2008-01-07 |
| `cq_20080108` | view | 10 | `date` 2008-01-08 to 2008-01-08 |
| `cq_20080109` | view | 10 | `date` 2008-01-09 to 2008-01-09 |
| `cq_20080110` | view | 10 | `date` 2008-01-10 to 2008-01-10 |
| `cq_20080111` | view | 10 | `date` 2008-01-11 to 2008-01-11 |
| `ct0002` | view (empty) | 10 | `date`, not asked |
| `ct_20080107` | view | 9 | `date` 2008-01-07 to 2008-01-07 |
| `ct_20080108` | view | 9 | `date` 2008-01-08 to 2008-01-08 |
| `ct_20080109` | view | 9 | `date` 2008-01-09 to 2008-01-09 |
| `ct_20080110` | view | 9 | `date` 2008-01-10 to 2008-01-10 |
| `ct_20080111` | view | 9 | `date` 2008-01-11 to 2008-01-11 |
| `div_200801` | view | 5 | `fdate` 2008-01-02 to 2008-01-31 |
| `mast_200801` | view | 18 | `fdate` 2003-12-18 to 2008-01-31 |

## taqsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `cq0002` | view (empty) | 11 | `date`, not asked |
| `cq_20080107` | 391,404,064 | 10 | `date`, not asked (too big) |
| `cq_20080108` | 402,661,408 | 10 | `date`, not asked (too big) |
| `cq_20080109` | 415,126,016 | 10 | `date`, not asked (too big) |
| `cq_20080110` | 437,381,216 | 10 | `date`, not asked (too big) |
| `cq_20080111` | 372,855,680 | 10 | `date`, not asked (too big) |
| `ct0002` | view (empty) | 10 | `date`, not asked |
| `ct_20080107` | 29,272,276 | 9 | `date`, not asked (too big) |
| `ct_20080108` | 30,301,558 | 9 | `date`, not asked (too big) |
| `ct_20080109` | 33,700,824 | 9 | `date`, not asked (too big) |
| `ct_20080110` | 33,697,244 | 9 | `date`, not asked (too big) |
| `ct_20080111` | 28,237,636 | 9 | `date`, not asked (too big) |
| `div_200801` | 952 | 5 | `fdate` 2008-01-02 to 2008-01-31 |
| `mast_200801` | 10,816 | 18 | `fdate` 2003-12-18 to 2008-01-31 |

## totalq

| table | rows | columns | dates |
|---|---|---|---|
| `total_q` | view | 8 | `datadate` 1950-06-30 to 2025-05-31 |

## totalq_all

| table | rows | columns | dates |
|---|---|---|---|
| `total_q` | 485,746 | 8 | `datadate` 1950-06-30 to 2025-05-31 |

## tr_sdc_samples

| table | rows | columns | dates |
|---|---|---|---|
| `calldata` | 167 | 12 | `cldat1` 2023-04-03 to 2043-07-01 |
| `deals_data` | 409 | 64 | `wrds_first_sale_date` 2022-01-12 to 2024-02-12 |
| `maturity` | 167 | 7 | `endserialmaty` 2025-07-01 to 2057-06-15 |
| `ratings` | 167 | 8 | - |
| `sdc_joint_ventures` | 328 | 125 | `aa_hdate` 2018-11-26 to 2038-12-31 |
| `wrds_bo_fund_firm` | 468 | 51 | `founded_fund` 1960-01-01 to 2022-01-01 |
| `wrds_bo_fundra_fund` | 268 | 34 | `report_date` 1992-03-31 to 2022-09-30 |
| `wrds_bo_invdtl_compn_fund` | 968 | 92 | `round_date` 2023-01-01 to 2024-01-25 |
| `wrds_managers` | 335 | 5 | - |
| `wrds_vc_fund_firm` | 508 | 51 | `founded_fund` 1972-01-01 to 2022-01-01 |
| `wrds_vc_fundra_fund` | 272 | 34 | `report_date` 1972-12-31 to 2022-06-30 |
| `wrds_vc_invdtl_compn_fund` | 2,170 | 92 | `round_date` 2023-01-04 to 2024-01-30 |

## trace

| table | rows | columns | dates |
|---|---|---|---|
| `absmasterfile` | view | 21 | `mtrty_dt` 2005-08-25 to 3999-12-31 |
| `camasterfile` | view | 18 | `mtrty_dt` 1991-06-01 to 9999-12-31 |
| `cmomasterfile` | view | 23 | `mtrty_dt` 1937-11-19 to 3888-12-31 |
| `mbsmasterfile` | view | 21 | `mtrty_dt` 1951-12-01 to 3999-12-31 |
| `mbsrdidmasterfile` | view | 12 | `stdt` 2021-07-01 to 2026-09-17 |
| `tbamasterfile` | view | 19 | `mtrty_dt` 2036-06-25 to 2046-08-15 |
| `trace` | view | 67 | `trans_dt` 2014-10-01 to 2026-09-17 |
| `trace_agency` | view | 67 | `trans_dt` 2012-08-01 to 2026-09-17 |
| `trace_agency_enhanced` | view | 42 | `trd_exctn_dt` 2010-04-01 to 2026-03-17 |
| `trace_btds144a` | view | 67 | `trans_dt` 2014-06-30 to 2026-09-17 |
| `trace_btds144a_enhanced` | view | 42 | `trd_exctn_dt` 2003-08-02 to 2026-03-17 |
| `trace_enhanced` | view | 42 | `trd_exctn_dt` 2002-07-01 to 2026-03-17 |
| `trace_spds144a_abs` | view | 55 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trace_spds144a_abs_enhanced` | view | 38 | `trd_exctn_dt` 2011-05-16 to 2025-03-17 |
| `trace_spds144a_cmo` | view | 55 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trace_spds144a_cmo_enhanced` | view | 38 | `trd_exctn_dt` 2011-05-13 to 2025-03-17 |
| `trace_spds_abs` | view | 56 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trace_spds_abs_enhanced` | view | 38 | `trd_exctn_dt` 2011-05-14 to 2025-03-17 |
| `trace_spds_cmo` | view | 56 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trace_spds_cmo_enhanced` | view | 38 | `trd_exctn_dt` 2011-05-11 to 2025-03-17 |
| `trace_spds_mbs` | view | 52 | `trans_dt` 2013-07-22 to 2026-09-17 |
| `trace_spds_mbs_enhanced` | view | 39 | `trd_exctn_dt` 2011-05-16 to 2025-03-17 |
| `trace_spds_tba` | view | 56 | `trans_dt` 2012-11-12 to 2026-09-17 |
| `trace_spds_tba_enhanced` | view | 38 | `trd_exctn_dt` 2011-05-10 to 2025-03-17 |
| `trade_summary` | view | 23 | `trans_dt` 2012-02-06 to 2026-09-17 |
| `trade_summary_agency` | view | 23 | `trans_dt` 2012-02-06 to 2026-09-17 |
| `trade_summary_btds144a` | view | 23 | `trans_dt` 2014-06-30 to 2026-09-17 |
| `trade_summary_spds144a_abs` | view | 16 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trade_summary_spds144a_cmo` | view | 16 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trade_summary_spds_abs` | view | 16 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trade_summary_spds_cmo` | view | 16 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trade_summary_spds_mbs` | view | 13 | `trans_dt` 2013-07-22 to 2026-09-17 |
| `trade_summary_spds_tba` | view | 16 | `trans_dt` 2012-11-13 to 2026-09-17 |

## trace_enhanced

| table | rows | columns | dates |
|---|---|---|---|
| `absmasterfile` | 776,595 | 21 | `mtrty_dt` 2005-08-25 to 3999-12-31 |
| `camasterfile` | 3,776,547 | 18 | `mtrty_dt` 1991-06-01 to 9999-12-31 |
| `cmomasterfile` | 17,376,712 | 23 | `mtrty_dt`, not asked (too big) |
| `mbsmasterfile` | 14,776,859 | 21 | `mtrty_dt`, not asked (too big) |
| `mbsrdidmasterfile` | 2,680,013 | 12 | `stdt` 2021-07-01 to 2026-09-17 |
| `tbamasterfile` | 157,586 | 19 | `mtrty_dt` 2036-06-25 to 2046-08-15 |
| `trace_agency_enhanced` | 17,236,184 | 42 | `trd_exctn_dt`, not asked (too big) |
| `trace_btds144a_enhanced` | 30,962,856 | 42 | `trd_exctn_dt`, not asked (too big) |
| `trace_enhanced` | 469,144,480 | 42 | `trd_exctn_dt`, not asked (too big) |
| `trace_spds144a_abs_enhanced` | 673,598 | 38 | `trd_exctn_dt` 2011-05-16 to 2025-03-17 |
| `trace_spds144a_cmo_enhanced` | 847,086 | 38 | `trd_exctn_dt` 2011-05-13 to 2025-03-17 |
| `trace_spds_abs_enhanced` | 1,175,943 | 38 | `trd_exctn_dt` 2011-05-14 to 2025-03-17 |
| `trace_spds_cmo_enhanced` | 8,205,238 | 38 | `trd_exctn_dt`, not asked (too big) |
| `trace_spds_mbs_enhanced` | 20,130,256 | 39 | `trd_exctn_dt`, not asked (too big) |
| `trace_spds_tba_enhanced` | 43,566,452 | 38 | `trd_exctn_dt`, not asked (too big) |

## trace_standard

| table | rows | columns | dates |
|---|---|---|---|
| `absmasterfile` | 776,595 | 21 | `mtrty_dt` 2005-08-25 to 3999-12-31 |
| `camasterfile` | 3,776,547 | 18 | `mtrty_dt` 1991-06-01 to 9999-12-31 |
| `cmomasterfile` | 17,376,712 | 23 | `mtrty_dt`, not asked (too big) |
| `mbsmasterfile` | 14,776,859 | 21 | `mtrty_dt`, not asked (too big) |
| `mbsrdidmasterfile` | 2,680,013 | 12 | `stdt` 2021-07-01 to 2026-09-17 |
| `tbamasterfile` | 160,832 | 19 | `mtrty_dt` 2036-06-25 to 2046-08-15 |
| `trace` | 327,670,144 | 67 | `trans_dt`, not asked (too big) |
| `trace_agency` | 15,178,705 | 67 | `trans_dt`, not asked (too big) |
| `trace_btds144a` | 22,576,584 | 67 | `trans_dt`, not asked (too big) |
| `trace_spds144a_abs` | 493,943 | 55 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trace_spds144a_cmo` | 206,784 | 55 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trace_spds_abs` | 795,390 | 56 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trace_spds_cmo` | 2,105,088 | 56 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trace_spds_mbs` | 15,400,939 | 52 | `trans_dt`, not asked (too big) |
| `trace_spds_tba` | 27,834,124 | 56 | `trans_dt`, not asked (too big) |
| `trade_summary` | 31,422,994 | 23 | `trans_dt`, not asked (too big) |
| `trade_summary_agency` | 2,179,883 | 23 | `trans_dt` 2012-02-06 to 2026-09-17 |
| `trade_summary_btds144a` | 5,098,581 | 23 | `trans_dt`, not asked (too big) |
| `trade_summary_spds144a_abs` | 302,229 | 16 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trade_summary_spds144a_cmo` | 94,320 | 16 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trade_summary_spds_abs` | 407,639 | 16 | `trans_dt` 2015-06-01 to 2026-09-17 |
| `trade_summary_spds_cmo` | 879,058 | 16 | `trans_dt` 2017-03-20 to 2026-09-17 |
| `trade_summary_spds_mbs` | 5,165,404 | 13 | `trans_dt`, not asked (too big) |
| `trade_summary_spds_tba` | 351,790 | 16 | `trans_dt` 2012-11-13 to 2026-09-17 |

## trcstsmp

| table | rows | columns | dates |
|---|---|---|---|
| `_chars_` | view (empty) | 3 | - |
| `wrds_carbon_data` | view | 6 | `periodenddate` 2019-03-02 to 2019-12-31 |
| `wrds_carbon_forecast` | view | 22 | `periodenddate` 2019-03-02 to 2019-12-31 |
| `wrds_companies` | view | 24 | - |
| `wrds_data_items` | view | 5 | - |
| `wrds_environment` | view | 203 | `periodenddate` 2018-12-31 to 2019-03-31 |
| `wrds_esg` | view | 41 | `scoredate` 2020-11-13 to 2021-03-25 |
| `wrds_esg_facts` | view | 21 | - |
| `wrds_ff_data` | view | 78 | `periodenddate` 2019-03-31 to 2019-12-31 |
| `wrds_ff_sector` | view | 91 | `periodenddate` 2019-03-31 to 2019-12-31 |
| `wrds_paris_data` | view | 20 | `extractiondate` 2020-04-01 to 2020-04-01 |
| `wrds_paris_emissions` | view | 46 | `extractiondate` 2020-04-01 to 2020-04-01 |
| `wrds_revenue` | view | 12 | `periodenddate` 2019-03-31 to 2019-12-31 |
| `wrds_risk_data` | view | 19 | `periodenddate`, not asked |
| `wrds_risk_forecast` | view | 43 | `periodenddate`, not asked |

## trdbdmismp

| table | rows | columns | dates |
|---|---|---|---|
| `dandb_dmi_us_2023` | view | 57 | `reportdate` 2010-02-28 to 2023-12-10 |

## trdbwbsmp

| table | rows | columns | dates |
|---|---|---|---|
| `dandb_wb_ap_business_2023` | view | 53 | - |
| `dandb_wb_ap_delete_2023` | view | 7 | - |
| `dandb_wb_ap_link_2023` | view | 152 | `fll_rpt_dt` 2014-09-20 to 2023-12-12 |
| `dandb_wb_ap_unlnk_2023` | view | 98 | `fll_rpt_dt` 2003-05-21 to 2023-10-05 |
| `dandb_wb_eu_business_2023` | view | 53 | - |
| `dandb_wb_eu_delete_2023` | view | 7 | - |
| `dandb_wb_eu_link_2023` | view | 152 | `fll_rpt_dt` 2021-10-23 to 2023-12-14 |
| `dandb_wb_eu_unlnk_2023` | view | 98 | `fll_rpt_dt` 1996-03-05 to 2023-10-09 |

## trdssamp

| table | rows | columns | dates |
|---|---|---|---|
| `ds2mktval` | view | 5 | `valdate` 2000-01-03 to 2021-05-19 |
| `ds2primqtprc` | view | 17 | `marketdate` 1965-01-01 to 2021-05-19 |
| `ds2primqtri` | view | 5 | `marketdate` 1964-12-30 to 2021-05-19 |
| `dscminfo` | view | 20 | `statusdate_` 2008-07-30 to 2020-04-25 |
| `dsfutcontrinfo` | view | 19 | `startdate` 1984-10-01 to 2020-10-16 |
| `ecodata` | view | 6 | `perioddate` 1945-01-01 to 2021-11-01 |
| `ecoinfo` | view | 25 | `startdate` 1948-01-01 to 2009-07-01 |
| `wrds_cmdy_data` | view | 25 | `date_` 1974-01-31 to 2020-11-18 |
| `wrds_cmdy_info` | view | 24 | `statusdate_` 2008-07-30 to 2020-04-25 |
| `wrds_contract_info` | view | 24 | `startdate` 1984-10-01 to 2020-10-16 |
| `wrds_cseries_info` | view | 12 | - |
| `wrds_ds2dsf` | view | 35 | `marketdate` 1965-01-01 to 2021-04-07 |
| `wrds_ds_indexconstmerged_dly` | view | 19 | `date_` 2008-08-07 to 2020-09-18 |
| `wrds_ds_indexconstmerged_mth` | view | 20 | `date_` 1920-03-31 to 2020-08-31 |
| `wrds_ds_indexmerged` | view | 17 | `basedate` 1986-09-03 to 2000-05-02 |
| `wrds_ds_names` | view | 39 | `delistdate`, not asked |
| `wrds_ecoinfo` | view | 31 | `startdate` 1948-01-01 to 2009-07-01 |
| `wrds_fut_contract` | view | 21 | `date_` 1984-10-01 to 2021-11-17 |
| `wrds_fut_series` | view | 25 | `date_` 1973-01-02 to 2021-11-18 |

## tresgsmp

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_ref_esg` | view | 17 | `valuedate` 2021-10-21 to 2024-02-03 |

## trsamp

| table | rows | columns | dates |
|---|---|---|---|
| `det_guidance` | view | 23 | `actdats` 2002-12-10 to 2013-10-17 |
| `productperformance` | view | 6 | `date` 1992-09-30 to 2014-04-30 |
| `wrds_company_cg` | view | 143 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_company_ec` | view | 47 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_company_en` | view | 194 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_company_info` | view | 11 | - |
| `wrds_company_smry` | view | 11 | `feeddate` 2020-11-08 to 2020-11-15 |
| `wrds_company_so` | view | 342 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_esg_boardmem` | view | 63 | `fyenddate`, not asked |
| `wrds_esg_drivers` | view | 149 | `feeddate` 2020-11-08 to 2020-11-15 |
| `wrds_esg_indagg` | view | 123 | - |
| `wrds_esg_outcomes` | view | 217 | `feeddate` 2020-11-08 to 2020-11-15 |
| `wrds_productdetails` | view | 185 | `closedtoinvestdate` 1995-08-31 to 2011-08-31 |
| `wrds_ws_company` | view | 67 | `item7015` 2000-04-03 to 2015-03-27 |
| `wrds_ws_funda` | view | 466 | `item5350` 1980-03-31 to 2014-12-31 |
| `wrds_ws_fundq` | view | 250 | `date_` 1997-09-30 to 2015-03-31 |
| `wrds_ws_ids` | view | 10 | - |
| `wrds_ws_pension` | view | 52 | - |
| `wrds_ws_segments` | view | 163 | `date_` 1988-01-31 to 2014-12-31 |
| `wrds_ws_stock` | view | 267 | `date_` 1980-03-31 to 2015-04-30 |
| `wrds_ws_stock_header` | view | 64 | `date_` 2000-08-31 to 2015-05-02 |

## trsamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `det_guidance` | 9,509 | 23 | `actdats` 2002-12-10 to 2013-10-17 |
| `productperformance` | 3,003 | 6 | `date` 1992-09-30 to 2014-04-30 |
| `wrds_company_cg` | 277 | 143 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_company_ec` | 277 | 47 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_company_en` | 277 | 194 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_company_info` | 19 | 11 | - |
| `wrds_company_smry` | 298 | 11 | `feeddate` 2020-11-08 to 2020-11-15 |
| `wrds_company_so` | 277 | 342 | `feeddate` 2020-08-02 to 2020-11-15 |
| `wrds_esg_boardmem` | 7,926 | 63 | `fyenddate`, not asked |
| `wrds_esg_drivers` | 298 | 149 | `feeddate` 2020-11-08 to 2020-11-15 |
| `wrds_esg_indagg` | 190 | 123 | - |
| `wrds_esg_outcomes` | 298 | 217 | `feeddate` 2020-11-08 to 2020-11-15 |
| `wrds_productdetails` | 50 | 185 | `closedtoinvestdate` 1995-08-31 to 2011-08-31 |

## trsamp_db_dmi

| table | rows | columns | dates |
|---|---|---|---|
| `dandb_dmi_us_2023` | 100 | 57 | `reportdate` 2010-02-28 to 2023-12-10 |

## trsamp_db_wb

| table | rows | columns | dates |
|---|---|---|---|
| `dandb_wb_ap_business_2023` | 606 | 53 | - |
| `dandb_wb_ap_delete_2023` | 450 | 7 | - |
| `dandb_wb_ap_link_2023` | 5,825 | 152 | `fll_rpt_dt` 2014-09-20 to 2023-12-12 |
| `dandb_wb_ap_unlnk_2023` | 796 | 98 | `fll_rpt_dt` 2003-05-21 to 2023-10-05 |
| `dandb_wb_eu_business_2023` | 589 | 53 | - |
| `dandb_wb_eu_delete_2023` | 438 | 7 | - |
| `dandb_wb_eu_link_2023` | 5,791 | 152 | `fll_rpt_dt` 2021-10-23 to 2023-12-14 |
| `dandb_wb_eu_unlnk_2023` | 1,238 | 98 | `fll_rpt_dt` 1996-03-05 to 2023-10-09 |

## trsamp_ds_eq

| table | rows | columns | dates |
|---|---|---|---|
| `ds2mktval` | 101,382 | 5 | `valdate` 2000-01-03 to 2021-05-19 |
| `ds2primqtprc` | 164,357 | 17 | `marketdate` 1965-01-01 to 2021-05-19 |
| `ds2primqtri` | 173,297 | 5 | `marketdate` 1964-12-30 to 2021-05-19 |
| `wrds_ds2dsf` | 161,761 | 35 | `marketdate` 1965-01-01 to 2021-04-07 |
| `wrds_ds_indexconstmerged_dly` | 12,167 | 19 | `date_` 2008-08-07 to 2020-09-18 |
| `wrds_ds_indexconstmerged_mth` | 11,443 | 20 | `date_` 1920-03-31 to 2020-08-31 |
| `wrds_ds_indexmerged` | 100 | 17 | `basedate` 1986-09-03 to 2000-05-02 |
| `wrds_ds_names` | 27 | 39 | `delistdate`, not asked |

## trsamp_dscom

| table | rows | columns | dates |
|---|---|---|---|
| `dscminfo` | 100 | 20 | `statusdate_` 2008-07-30 to 2020-04-25 |
| `wrds_cmdy_data` | 247,540 | 25 | `date_` 1974-01-31 to 2020-11-18 |
| `wrds_cmdy_info` | 100 | 24 | `statusdate_` 2008-07-30 to 2020-04-25 |

## trsamp_dsecon

| table | rows | columns | dates |
|---|---|---|---|
| `ecodata` | 5,948,240 | 6 | `perioddate`, not asked (too big) |
| `ecoinfo` | 50 | 25 | `startdate` 1948-01-01 to 2009-07-01 |
| `wrds_ecoinfo` | 50 | 31 | `startdate` 1948-01-01 to 2009-07-01 |

## trsamp_dsfut

| table | rows | columns | dates |
|---|---|---|---|
| `dsfutcontrinfo` | 100 | 19 | `startdate` 1984-10-01 to 2020-10-16 |
| `wrds_contract_info` | 100 | 24 | `startdate` 1984-10-01 to 2020-10-16 |
| `wrds_cseries_info` | 825 | 12 | - |
| `wrds_fut_contract` | 34,377 | 21 | `date_` 1984-10-01 to 2021-11-17 |
| `wrds_fut_series` | 13,793,837 | 25 | `date_`, not asked (too big) |

## trsamp_esg

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_ref_esg` | 1,002 | 17 | `valuedate` 2021-10-21 to 2024-02-03 |

## trsamp_sdc_ma

| table | rows | columns | dates |
|---|---|---|---|
| `ma_advisors` | 733 | 22 | `dateann` 2016-03-13 to 2016-03-19 |
| `ma_details` | 2,373 | 168 | `dateann` 2016-03-13 to 2016-03-19 |
| `ma_events` | 1,433 | 10 | `dateann` 2016-03-13 to 2016-03-19 |

## trsamp_sdc_ni

| table | rows | columns | dates |
|---|---|---|---|
| `ni_details` | 6,647 | 158 | `master_deal_date` 2016-03-14 to 2016-03-19 |

## trsamp_worldscope

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_ws_company` | 101 | 67 | `item7015` 2000-04-03 to 2015-03-27 |
| `wrds_ws_funda` | 1,395 | 466 | `item5350` 1980-03-31 to 2014-12-31 |
| `wrds_ws_fundq` | 2,991 | 250 | `date_` 1997-09-30 to 2015-03-31 |
| `wrds_ws_ids` | 101 | 10 | - |
| `wrds_ws_pension` | 191 | 52 | - |
| `wrds_ws_segments` | 869 | 163 | `date_` 1988-01-31 to 2014-12-31 |
| `wrds_ws_stock` | 1,413 | 267 | `date_` 1980-03-31 to 2015-04-30 |
| `wrds_ws_stock_header` | 94 | 64 | `date_` 2000-08-31 to 2015-05-02 |

## trucost_samp

| table | rows | columns | dates |
|---|---|---|---|
| `_chars_` | view (empty) | 3 | - |
| `wrds_carbon_data` | 32 | 6 | `periodenddate` 2019-03-02 to 2019-12-31 |
| `wrds_carbon_forecast` | 452 | 22 | `periodenddate` 2019-03-02 to 2019-12-31 |
| `wrds_companies` | 78 | 24 | - |
| `wrds_data_items` | 1,952 | 5 | - |
| `wrds_environment` | 2 | 203 | `periodenddate` 2018-12-31 to 2019-03-31 |
| `wrds_esg` | 1,562 | 41 | `scoredate` 2020-11-13 to 2021-03-25 |
| `wrds_esg_facts` | 1,563 | 21 | - |
| `wrds_ff_data` | 5 | 78 | `periodenddate` 2019-03-31 to 2019-12-31 |
| `wrds_ff_sector` | 5 | 91 | `periodenddate` 2019-03-31 to 2019-12-31 |
| `wrds_paris_data` | 9 | 20 | `extractiondate` 2020-04-01 to 2020-04-01 |
| `wrds_paris_emissions` | 9 | 46 | `extractiondate` 2020-04-01 to 2020-04-01 |
| `wrds_revenue` | 25 | 12 | `periodenddate` 2019-03-31 to 2019-12-31 |
| `wrds_risk_data` | 9 | 19 | `periodenddate`, not asked |
| `wrds_risk_forecast` | 65 | 43 | `periodenddate`, not asked |

## twoiq_samp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 35 | `inputdate`, not asked |
| `insiderfeedglobal` | 38,937 | 35 | `inputdate` 2000-01-06 to 2016-04-21 |
| `insiderfeedglobalaggregated` | 10,418 | 33 | `tradedate` 1999-01-06 to 2016-04-20 |

## twoiqsmp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 35 | `inputdate`, not asked |
| `insiderfeedglobal` | view | 35 | `inputdate` 2000-01-06 to 2016-04-21 |
| `insiderfeedglobalaggregated` | view | 33 | `tradedate` 1999-01-06 to 2016-04-20 |

## wabssamp

| table | rows | columns | dates |
|---|---|---|---|
| `autolease` | view | 70 | `fdate` 2017-02-24 to 2017-12-27 |
| `autoloan` | view | 76 | `fdate` 2017-01-12 to 2017-12-27 |
| `cmbs` | view | 155 | `fdate` 2017-01-24 to 2017-12-29 |
| `debtsecurities` | view | 64 | `fdate` 2020-12-10 to 2020-12-10 |

## wappsamp

| table | rows | columns | dates |
|---|---|---|---|
| `ccmxpf_lnkhist` | view | 4 | `linkdt` 1962-01-02 to 2013-10-04 |
| `ciqkeydev` | view | 2 | - |
| `ciqkeydevint` | view | 2 | - |
| `country` | view | 6 | `startdate` 1999-01-01 to 1999-01-01 |
| `dsedelist` | view | 3 | `dlstdt` 2010-01-05 to 2013-12-31 |
| `dsf` | view | 5 | `date` 2010-01-04 to 2013-12-31 |
| `dsi` | view | 1 | `date` 2010-01-04 to 2013-12-31 |
| `g_secd` | view | 11 | `datadate` 2010-01-01 to 2013-12-31 |
| `g_security` | view | 2 | - |
| `series_data` | view | 3 | `date` 2010-01-01 to 2013-12-31 |
| `wrds_keydev` | view | 5 | `announcedate` 2010-01-02 to 2013-12-31 |
| `wrds_keydevint` | view | 5 | `announcedate` 2010-01-01 to 2013-12-31 |

## wenvsmp

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_air` | view | 770 | `env_header_date` 1949-11-28 to 2039-01-10 |
| `wrds_facilities` | view | 287 | `env_header_date` 1949-11-28 to 2039-01-10 |
| `wrds_geography` | view | 95 | - |
| `wrds_water` | view | 104 | `env_header_date` 1949-11-28 to 2039-01-10 |

## wmfsmp

| table | rows | columns | dates |
|---|---|---|---|
| `fund_12b1_payments` | view | 12 | - |
| `fund_administrator` | view | 11 | - |
| `fund_adviser` | view | 12 | - |
| `fund_advisory_contract` | view | 54 | - |
| `fund_alt_investment` | view | 38 | - |
| `fund_balance_sheet` | view | 35 | - |
| `fund_broker_dealer` | view | 5 | - |
| `fund_broker_relations` | view | 17 | - |
| `fund_custodian` | view | 18 | - |
| `fund_debt_invest` | view | 25 | - |
| `fund_equity_invest` | view | 13 | - |
| `fund_family` | view | 6 | - |
| `fund_income_statement` | view | 38 | - |
| `fund_monthly_sales_repurchases` | view | 12 | - |
| `fund_public_accountant` | view | 10 | - |
| `fund_registrant` | view | 53 | `report_date` 2005-11-30 to 2018-05-31 |
| `fund_registrant_broker_com` | view | 7 | - |
| `fund_shrh_sev_agent` | view | 9 | - |
| `fund_transaction_principals` | view | 9 | - |
| `fund_underwriter` | view | 11 | - |
| `nsar_headers` | view | 10 | `fdate` 2006-02-23 to 2019-06-04 |

## wrds_abs_samp

| table | rows | columns | dates |
|---|---|---|---|
| `autolease` | 4,010,137 | 70 | `fdate` 2017-02-24 to 2017-12-27 |
| `autoloan` | 19,010,460 | 76 | `fdate`, not asked (too big) |
| `cmbs` | 36,676 | 155 | `fdate` 2017-01-24 to 2017-12-29 |
| `debtsecurities` | 1 | 64 | `fdate` 2020-12-10 to 2020-12-10 |

## wrds_environmental_samp

| table | rows | columns | dates |
|---|---|---|---|
| `wrds_air` | 1,458 | 770 | `env_header_date` 1949-11-28 to 2039-01-10 |
| `wrds_facilities` | 100 | 287 | `env_header_date` 1949-11-28 to 2039-01-10 |
| `wrds_geography` | 3,240 | 95 | - |
| `wrds_water` | 1,823 | 104 | `env_header_date` 1949-11-28 to 2039-01-10 |

## wrds_insiders_samp

| table | rows | columns | dates |
|---|---|---|---|
| `fdic_derivatives` | 15 | 27 | `filing_date` 2023-07-26 to 2023-09-29 |
| `fdic_document_info` | 126 | 18 | `filing_date` 2023-07-03 to 2023-09-29 |
| `fdic_footnotes` | 82 | 5 | `filing_date` 2023-07-03 to 2023-09-25 |
| `fdic_nonderivatives` | 206 | 20 | `filing_date` 2023-07-03 to 2023-09-29 |
| `fdic_reporting_owners` | 107 | 18 | `filing_date` 2023-07-03 to 2023-09-29 |
| `fdic_signatures` | 107 | 8 | `filing_date` 2023-07-03 to 2023-09-29 |
| `sec_derivatives` | 499 | 28 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_document_info` | 607 | 24 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_footnotes` | 2,730 | 11 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_nonderivatives` | 1,187 | 21 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_reporting_owners` | 680 | 21 | `fdate` 2023-09-01 to 2023-09-01 |
| `sec_signatures` | 630 | 6 | `signaturedate` 2023-09-01 to 2023-09-01 |
| `secbert_footnotes` | 2,730 | 27 | `fdate` 2023-09-01 to 2023-09-01 |
| `wrds_nara_filings` | 1,304 | 31 | `filing_date` 2001-03-12 to 2001-03-12 |
| `wrds_table_1` | 1,539 | 62 | `filing_date` 2023-07-03 to 2023-09-29 |
| `wrds_table_2` | 523 | 69 | `filing_date` 2023-07-26 to 2023-09-29 |
| `wrds_table_3` | 41 | 44 | `filing_date` 2023-09-01 to 2023-09-05 |

## wrds_mutualfund_samp

| table | rows | columns | dates |
|---|---|---|---|
| `fund_12b1_payments` | 4,787 | 12 | - |
| `fund_administrator` | 715 | 11 | - |
| `fund_adviser` | 7,068 | 12 | - |
| `fund_advisory_contract` | 6,984 | 54 | - |
| `fund_alt_investment` | 7,088 | 38 | - |
| `fund_balance_sheet` | 7,105 | 35 | - |
| `fund_broker_dealer` | 3,895 | 5 | - |
| `fund_broker_relations` | 16,072 | 17 | - |
| `fund_custodian` | 34,298 | 18 | - |
| `fund_debt_invest` | 6,561 | 25 | - |
| `fund_equity_invest` | 6,973 | 13 | - |
| `fund_family` | 919 | 6 | - |
| `fund_income_statement` | 7,105 | 38 | - |
| `fund_monthly_sales_repurchases` | 42,618 | 12 | - |
| `fund_public_accountant` | 838 | 10 | - |
| `fund_registrant` | 20,163 | 53 | `report_date` 2005-11-30 to 2018-05-31 |
| `fund_registrant_broker_com` | 4,641 | 7 | - |
| `fund_shrh_sev_agent` | 709 | 9 | - |
| `fund_transaction_principals` | 5,135 | 9 | - |
| `fund_underwriter` | 587 | 11 | - |
| `nsar_headers` | 29,626 | 10 | `fdate` 2006-02-23 to 2019-06-04 |

## wrds_shortvolume_samp

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 1 | - |
| `wrds_shortvolume_samp` | 15,883 | 46 | `date` 2015-01-02 to 2020-12-31 |

## wrdsapps

| table | rows | columns | dates |
|---|---|---|---|
| `bondcrsp_link` | view | 9 | `trace_startdt` 2002-07-01 to 2025-12-31 |
| `chars` | view (empty) | 93 | `fndate`, not asked |
| `compeushortlink` | view | 6 | - |
| `country` | view | 6 | `startdate` 1999-01-01 to 2007-01-24 |
| `dwcountryreturns` | view | 7 | `date` 1986-07-01 to 2026-06-26 |
| `eushort` | view | 10 | `position_date` 2003-03-26 to 2026-09-24 |
| `exec_boardex` | view | 23 | - |
| `exec_boardex_link` | view | 16 | - |
| `firm_ratio` | view | 98 | `adate` 1968-12-31 to 2025-10-31 |
| `fscrsplink` | view | 18 | `link_bdate` 1962-07-02 to 2025-12-31 |
| `id` | view | 4 | - |
| `intl_market_values` | view | 4 | - |
| `intl_security_returns` | view | 3 | - |
| `mwcountryreturns` | view | 6 | `date` 1986-07-30 to 2026-06-26 |
| `tclink` | view | 10 | `date` 1993-01-31 to 2014-12-31 |
| `usa_market_values` | view | 3 | - |
| `usa_security_returns` | view | 3 | - |
| `uspatents_citations` | view | 7 | `grantdate` 2011-01-04 to 2019-12-31 |
| `uspatents_gvkey_linking` | view | 8 | `link_bdate` 2011-01-04 to 2019-12-31 |
| `uspatents_meta` | view | 17 | `grantdate` 2011-01-04 to 2019-12-31 |
| `wcountryconstituents` | view | 8 | `junedate` 1990-06-29 to 2026-06-26 |
| `wrds_relationships` | view | 16 | `fdate` 1993-12-22 to 2025-02-26 |

## wrdsapps_eushort

| table | rows | columns | dates |
|---|---|---|---|
| `eushort` | 441,393 | 10 | `position_date` 2003-03-26 to 2026-09-24 |

## wrdsapps_evtstudy_int

| table | rows | columns | dates |
|---|---|---|---|
| `intl_market_values` | 77 | 4 | - |
| `intl_security_returns` | 58,848 | 3 | - |

## wrdsapps_evtstudy_int_ginsight

| table | rows | columns | dates |
|---|---|---|---|
| `country` | 48 | 6 | `startdate` 1999-01-01 to 2007-01-24 |

## wrdsapps_evtstudy_us

| table | rows | columns | dates |
|---|---|---|---|
| `usa_market_values` | 12 | 3 | - |
| `usa_security_returns` | 37,776 | 3 | - |

## wrdsapps_finratio

| table | rows | columns | dates |
|---|---|---|---|
| `firm_ratio` | 2,898,524 | 98 | `adate` 1968-12-31 to 2025-10-31 |
| `id` | 45,920 | 4 | - |

## wrdsapps_link_comp_eushort

| table | rows | columns | dates |
|---|---|---|---|
| `compeushortlink` | 5,409 | 6 | - |

## wrdsapps_link_crsp_bond

| table | rows | columns | dates |
|---|---|---|---|
| `bondcrsp_link` | 383,120 | 9 | `trace_startdt` 2002-07-01 to 2025-12-31 |

## wrdsapps_link_crsp_factset

| table | rows | columns | dates |
|---|---|---|---|
| `fscrsplink` | 343,249 | 18 | `link_bdate` 1962-07-02 to 2025-12-31 |

## wrdsapps_link_crsp_taq

| table | rows | columns | dates |
|---|---|---|---|
| `tclink` | 1,988,835 | 10 | `date` 1993-01-31 to 2014-12-31 |

## wrdsapps_patents

| table | rows | columns | dates |
|---|---|---|---|
| `uspatents_citations` | 54,367,948 | 7 | `grantdate`, not asked (too big) |
| `uspatents_gvkey_linking` | 1,471,276 | 8 | `link_bdate` 2011-01-04 to 2019-12-31 |
| `uspatents_meta` | 2,792,128 | 17 | `grantdate` 2011-01-04 to 2019-12-31 |

## wrdsapps_plink_exec_boardex

| table | rows | columns | dates |
|---|---|---|---|
| `exec_boardex` | 68,723 | 23 | - |
| `exec_boardex_link` | 44,373 | 16 | - |

## wrdsapps_subsidiary

| table | rows | columns | dates |
|---|---|---|---|
| `chars` | view (empty) | 93 | `fndate`, not asked |
| `wrds_relationships` | 12,306,709 | 16 | `fdate`, not asked (too big) |

## wrdsapps_windices

| table | rows | columns | dates |
|---|---|---|---|
| `dwcountryreturns` | 298,845 | 7 | `date` 1986-07-01 to 2026-06-26 |
| `mwcountryreturns` | 13,817 | 6 | `date` 1986-07-30 to 2026-06-26 |
| `wcountryconstituents` | 379,134 | 8 | `junedate` 1990-06-29 to 2026-06-26 |

## wrdsappssamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `ccmxpf_lnkhist` | 1,927 | 4 | `linkdt` 1962-01-02 to 2013-10-04 |
| `ciqkeydev` | 24,164 | 2 | - |
| `ciqkeydevint` | 184,816 | 2 | - |
| `country` | 4 | 6 | `startdate` 1999-01-01 to 1999-01-01 |
| `dsedelist` | 1,551 | 3 | `dlstdt` 2010-01-05 to 2013-12-31 |
| `dsf` | 6,759,308 | 5 | `date`, not asked (too big) |
| `dsi` | 1,006 | 1 | `date` 2010-01-04 to 2013-12-31 |
| `g_secd` | 5,411,561 | 11 | `datadate`, not asked (too big) |
| `g_security` | 21 | 2 | - |
| `series_data` | 5,839 | 3 | `date` 2010-01-01 to 2013-12-31 |
| `wrds_keydev` | 24,169 | 5 | `announcedate` 2010-01-02 to 2013-12-31 |
| `wrds_keydevint` | 185,845 | 5 | `announcedate` 2010-01-01 to 2013-12-31 |

## wrdssec_midas

| table | rows | columns | dates |
|---|---|---|---|
| `security` | 21,149,700 | 26 | `date`, not asked (too big) |

## zacksamp

| table | rows | columns | dates |
|---|---|---|---|
| `company_info` | view | 6 | - |
| `eps_actuals` | view | 5 | `reference_period` 1982-06-30 to 2012-06-30 |
| `eps_cons_daily` | view | 12 | `reference_period` 1979-09-30 to 2016-12-31 |
| `eps_cons_weekly` | view | 12 | `reference_period` 1979-09-30 to 2016-12-31 |
| `eps_detail` | view | 9 | `estimate_date` 1978-08-30 to 2012-10-26 |
| `eps_ltg_cons_daily` | view | 12 | `reference_period`, not asked |
| `eps_ltg_cons_weekly` | view | 12 | `reference_period`, not asked |
| `eps_surp` | view | 12 | `entry_date` 1994-10-18 to 2012-10-30 |
| `preann` | view | 18 | `reference_period` 1990-09-01 to 2013-01-01 |
| `ratings_cons_daily` | view | 12 | `observation_date` 1982-01-04 to 2012-10-19 |
| `ratings_cons_weekly` | view | 12 | `observation_date` 1982-01-08 to 2012-10-19 |
| `sales_cons` | view | 11 | `reference_period` 2000-03-31 to 2018-12-31 |
| `sales_surp` | view | 13 | `reference_period` 2000-12-31 to 2012-09-30 |
| `sales_terminations` | view | 5 | `reference_period` 2000-03-31 to 2018-12-31 |
| `samp_zids` | view | 1 | - |
| `tgtprice_cons` | view | 11 | `observation_date` 2000-01-01 to 2012-09-27 |
| `tgtprice_terminations` | view | 3 | `terminate_date` 2001-08-17 to 2012-10-01 |

## zacksamp_all

| table | rows | columns | dates |
|---|---|---|---|
| `company_info` | 17 | 6 | - |
| `eps_actuals` | 734 | 5 | `reference_period` 1982-06-30 to 2012-06-30 |
| `eps_cons_daily` | 120,871 | 12 | `reference_period` 1979-09-30 to 2016-12-31 |
| `eps_cons_weekly` | 79,885 | 12 | `reference_period` 1979-09-30 to 2016-12-31 |
| `eps_detail` | 80,368 | 9 | `estimate_date` 1978-08-30 to 2012-10-26 |
| `eps_ltg_cons_daily` | 8,354 | 12 | `reference_period`, not asked |
| `eps_ltg_cons_weekly` | 6,708 | 12 | `reference_period`, not asked |
| `eps_surp` | 857 | 12 | `entry_date` 1994-10-18 to 2012-10-30 |
| `preann` | 459 | 18 | `reference_period` 1990-09-01 to 2013-01-01 |
| `ratings_cons_daily` | 6,517 | 12 | `observation_date` 1982-01-04 to 2012-10-19 |
| `ratings_cons_weekly` | 4,984 | 12 | `observation_date` 1982-01-08 to 2012-10-19 |
| `sales_cons` | 28,724 | 11 | `reference_period` 2000-03-31 to 2018-12-31 |
| `sales_surp` | 501 | 13 | `reference_period` 2000-12-31 to 2012-09-30 |
| `sales_terminations` | 1,048 | 5 | `reference_period` 2000-03-31 to 2018-12-31 |
| `samp_zids` | 17 | 1 | - |
| `tgtprice_cons` | 4,455 | 11 | `observation_date` 2000-01-01 to 2012-09-27 |
| `tgtprice_terminations` | 17 | 3 | `terminate_date` 2001-08-17 to 2012-10-01 |

## Schemas the login has no access to

1574 schemas. The names are listed so that a later question "do we have X" can be answered here.

`aha_annual_survey_hist`, `aha_annual_survey_hist_new`, `aha_common`, `aha_common_old`, `aha_hcris_3years`,
`aha_hcris_3years_old`, `aha_hcris_recent`, `aha_hcris_recent_old`, `aha_it_survey_3years`,
`aha_it_survey_3years_old`, `aha_it_survey_recent`, `aha_it_survey_recent_old`, `aha_sample_old`, `altrata_exec_eur`,
`altrata_exec_eur_old`, `altrata_exec_na`, `altrata_exec_na_old`, `altrata_exec_row`, `altrata_exec_row_old`,
`altrata_exec_samp_old`, `altrata_exec_uk`, `altrata_exec_uk_old`, `audit_acct_os_old`, `audit_audit_comp_old`,
`audit_common_old`, `audit_corp_legal`, `audit_corp_legal_old`, `audit_esg_funds`, `audit_esg_funds_old`,
`audit_europe_old`, `audit_oia_old`, `audit_sedar`, `audit_sedar_old`, `bank_all_old`, `bank_premium`,
`bank_premium_new`, `bank_premium_old`, `bank_premium_samp_old`, `boardex_eur_old`, `boardex_na_old`, `boardex_row`,
`boardex_row_old`, `boardex_trial_old`, `boardex_uk_old`, `bvd_ama_large`, `bvd_ama_large_old`, `bvd_ama_medium`,
`bvd_ama_medium_old`, `bvd_ama_small`, `bvd_ama_small_old`, `bvd_ama_verylarge`, `bvd_ama_verylarge_old`,
`bvd_bvdbankf`, `bvd_bvdbankf_old`, `bvd_orbis_large`, `bvd_orbis_large_old`, `bvd_orbis_medium`,
`bvd_orbis_medium_old`, `bvd_orbis_small`, `bvd_orbis_small_old`, `bvd_osiris`, `bvd_osiris_old`, `calcbench_ap_ar`,
`calcbench_ap_ar_old`, `calcbench_business_combinations`, `calcbench_business_combinations_old`,
`calcbench_business_segments`, `calcbench_business_segments_old`, `calcbench_commitment_contingency`,
`calcbench_commitment_contingency_old`, `calcbench_common`, `calcbench_common_new`, `calcbench_common_old`,
`calcbench_concentration_risk`, `calcbench_concentration_risk_old`, `calcbench_derivatives_hedging`,
`calcbench_derivatives_hedging_old`, `calcbench_discontinued_ops`, `calcbench_discontinued_ops_old`,
`calcbench_equity_compensation`, `calcbench_equity_compensation_old`, `calcbench_equity_investments`,
`calcbench_equity_investments_old`, `calcbench_equity_repurchases`, `calcbench_equity_repurchases_old`,
`calcbench_fair_value`, `calcbench_fair_value_old`, `calcbench_goodwill`, `calcbench_goodwill_old`,
`calcbench_income_tax`, `calcbench_income_tax_old`, `calcbench_inventory`, `calcbench_inventory_old`,
`calcbench_leases`, `calcbench_leases_old`, `candid_3yr`, `candid_3yr_old`, `candid_6yr`, `candid_6yr_old`,
`candid_9yr`, `candid_9yr_old`, `candid_samp_old`, `cboe_all_old`, `cboe_eod`, `cboe_eod_new`, `cboe_eod_old`,
`cboe_sample_old`, `ciq_capstrct`, `ciq_capstrct_old`, `ciq_common`, `ciq_common_old`, `ciq_keydev`,
`ciq_keydev_old`, `ciq_pplintel`, `ciq_pplintel_old`, `ciq_ratings`, `ciq_ratings_old`, `ciq_transactions`,
`ciq_transactions_old`, `ciq_transcripts`, `ciq_transcripts_new`, `ciq_transcripts_old`, `ciqsamp_capstrct_old`,
`ciqsamp_common_old`, `ciqsamp_pplintel_old`, `ciqsamp_ratings_old`, `ciqsamp_transactions_old`, `columnar_internal`,
`comp_bank_daily_old`, `comp_execucomp_old`, `comp_filings`, `comp_global_daily_old`, `comp_na_daily_all_old`,
`comp_na_daily_current_old`, `comp_ph`, `comp_ph_old`, `comp_pit`, `comp_pit_old`, `comp_ratings`,
`comp_segments_hist_daily_old`, `comp_snapshot_old`, `comp_urq`, `comp_urq_old`, `compsamp_computext_old`,
`comscore_2002`, `comscore_2002_new`, `comscore_2002_old`, `comscore_2004`, `comscore_2004_new`, `comscore_2004_old`,
`comscore_2006`, `comscore_2006_new`, `comscore_2006_old`, `comscore_2007`, `comscore_2007_new`, `comscore_2007_old`,
`comscore_2008`, `comscore_2008_new`, `comscore_2008_old`, `comscore_2009`, `comscore_2009_new`, `comscore_2009_old`,
`comscore_2010`, `comscore_2010_new`, `comscore_2010_old`, `comscore_2011`, `comscore_2011_new`, `comscore_2011_old`,
`comscore_2012`, `comscore_2012_new`, `comscore_2012_old`, `comscore_2013`, `comscore_2013_new`, `comscore_2013_old`,
`comscore_2014`, `comscore_2014_new`, `comscore_2014_old`, `comscore_2015`, `comscore_2015_new`, `comscore_2015_old`,
`comscore_2016`, `comscore_2016_new`, `comscore_2016_old`, `comscore_2017`, `comscore_2017_new`, `comscore_2017_old`,
`comscore_2018`, `comscore_2018_new`, `comscore_2018_old`, `comscore_2019`, `comscore_2019_new`, `comscore_2019_old`,
`comscore_2020`, `comscore_2020_new`, `comscore_2020_old`, `comscore_2021`, `comscore_2021_new`, `comscore_2021_old`,
`comscore_2022`, `comscore_2022_new`, `comscore_2022_old`, `comscore_2023`, `comscore_2023_new`, `comscore_2023_old`,
`comscore_2024`, `comscore_2024_new`, `comscore_2024_old`, `comscore_2025`, `comscore_2025_new`, `comscore_2025_old`,
`comscore_common`, `comscore_common_new`, `comscore_common_old`, `contrib_bond_dickerson`,
`contrib_bond_dickerson_old`, `contrib_bond_firm_link`, `contrib_bond_firm_link_old`,
`contrib_corp_fed_litigation_old`, `contrib_corporate_bond_returns`, `contrib_corporate_bond_returns_old`,
`contrib_corporate_culture_old`, `contrib_general_old`, `contrib_global_factor_old`, `contrib_green_returns`,
`contrib_liquidity_taq`, `contrib_liquidity_taq_old`, `contrib_patent_firm_link_old`, `contrib_shale_old`,
`crsp_a_ccm`, `crsp_a_ccm_new`, `crsp_a_ccm_old`, `crsp_a_indexes`, `crsp_a_indexes_new`, `crsp_a_indexes_old`,
`crsp_a_stock10`, `crsp_a_stock62`, `crsp_a_stock62_new`, `crsp_a_stock62_old`, `crsp_a_stock_old`,
`crsp_a_treasuries`, `crsp_a_treasuries_old`, `crsp_a_ziman`, `crsp_a_ziman_old`, `crsp_m_ccm`, `crsp_m_ccm_new`,
`crsp_m_ccm_old`, `crsp_m_indexes`, `crsp_m_indexes_new`, `crsp_m_indexes_old`, `crsp_m_stock`, `crsp_m_stock62`,
`crsp_m_stock62_new`, `crsp_m_stock62_old`, `crsp_m_stock_new`, `crsp_m_stock_old`, `crsp_m_treasuries`,
`crsp_m_treasuries_old`, `crsp_m_ziman`, `crsp_m_ziman_old`, `crsp_q_ccm`, `crsp_q_ccm_old`, `crsp_q_indexes`,
`crsp_q_indexes_new`, `crsp_q_indexes_old`, `crsp_q_indexhist_old`, `crsp_q_mi_hist`, `crsp_q_mi_hist_old`,
`crsp_q_mutualfunds`, `crsp_q_mutualfunds_old`, `crsp_q_stock`, `crsp_q_stock62`, `crsp_q_stock62_new`,
`crsp_q_stock62_old`, `crsp_q_stock_new`, `crsp_q_stock_old`, `crsp_q_treasuries`, `crsp_q_treasuries_old`,
`crsp_q_ziman`, `crsp_q_ziman_old`, `crspsamp_all_old`, `csmar_af`, `csmar_af_old`, `csmar_cd`, `csmar_cd_old`,
`csmar_cg`, `csmar_cg_old`, `csmar_colc`, `csmar_colc_old`, `csmar_financial`, `csmar_financial_old`, `csmar_funds`,
`csmar_funds_old`, `csmar_hld`, `csmar_hld_old`, `csmar_ini`, `csmar_ini_old`, `csmar_ipo_a`, `csmar_ipo_a_old`,
`csmar_ma`, `csmar_ma_old`, `csmar_rs`, `csmar_rs_old`, `csmar_trade`, `csmar_trade_old`, `cusip_all`,
`datastream_wscope`, `django_wrds_web`, `estimize_estimates_consensus`, `estimize_estimates_consensus_old`,
`etfg_analytics`, `etfg_analytics_old`, `etfg_constituents`, `etfg_constituents_old`, `etfg_fund_flow`,
`etfg_fund_flow_old`, `etfg_industry`, `etfg_industry_old`, `evts_all`, `evts_all_new`, `evts_all_old`, `extensions`,
`factset_common`, `factset_common_old`, `factset_ff_int`, `factset_ff_int_old`, `factset_ff_usc`,
`factset_ff_usc_old`, `factset_own`, `factset_own_old`, `factset_revere_common`, `factset_revere_common_old`,
`factset_revere_geo_rev`, `factset_revere_geo_rev_old`, `factset_revere_ind_class`, `factset_revere_ind_class_old`,
`factset_revere_supply_chain`, `factset_revere_supply_chain_old`, `ff_all_old`, `fisd_common`, `fisd_common_old`,
`fisd_fisd`, `fisd_fisd_old`, `fisd_naic`, `fisd_naic_old`, `fjc_linking_old`, `fjc_litigation_old`, `form_metadata`,
`form_metadata_20230206`, `frb_all_old`, `ftse_russell_us`, `ftse_russell_us_old`, `gmi_all`, `hfr_academic_dead`,
`hfr_academic_dead_old`, `hfr_academic_live`, `hfr_academic_live_old`, `hfr_hfrdb`, `hfr_hfrdb_cn`,
`hfr_hfrdb_cn_old`, `hfr_hfrdb_dead`, `hfr_hfrdb_dead_cn`, `hfr_hfrdb_dead_cn_old`, `hfr_hfrdb_dead_old`,
`hfr_hfrdb_old`, `ims_hist_3yr_obp_premium`, `ims_hist_3yr_obp_standard_plus`, `ims_hist_5yr_obp_premium`,
`ims_hist_5yr_obp_standard_plus`, `ims_hist_obp_premium`, `ims_hist_obp_standard`, `ims_hist_obp_standard_plus`,
`ims_obp_premium`, `ims_obp_standard`, `ims_obp_standard_plus`, `infogroup_business_academic`,
`infogroup_business_academic_new`, `infogroup_business_academic_old`, `infogroup_residential`,
`infogroup_residential_new`, `infogroup_residential_old`, `information_schema`, `infraclear_metadata`,
`infraclear_metadata_old`, `infraclear_samp_old`, `infraclear_sector_ind`, `infraclear_sector_ind_old`,
`infraclear_sector_mog`, `infraclear_sector_mog_old`, `infraclear_sector_mshd`, `infraclear_sector_mshd_old`,
`infraclear_sector_pow`, `infraclear_sector_pow_old`, `infraclear_sector_trn`, `infraclear_sector_trn_old`,
`infraclear_sector_tsc`, `infraclear_sector_tsc_old`, `iss_climate_core`, `iss_climate_core_old`,
`iss_climate_emissions_old`, `iss_climate_energy`, `iss_climate_energy_old`, `iss_climate_impact`,
`iss_climate_impact_old`, `iss_climate_physical_risk`, `iss_climate_physical_risk_old`, `iss_compensation_analytics`,
`iss_compensation_analytics_old`, `iss_compensation_peers`, `iss_compensation_peers_old`, `iss_directors_global_old`,
`iss_incentive_lab`, `iss_incentive_lab_europe`, `iss_incentive_lab_europe_old`, `iss_incentive_lab_old`,
`iss_va_mf_new`, `iss_va_mf_old`, `iss_va_shareholder_new`, `iss_va_shareholder_old`, `iss_va_vote_global_new`,
`iss_va_vote_global_old`, `iss_va_vote_us_new`, `iss_va_vote_us_old`, `issm_all`, `issm_common`, `issm_nasd1987`,
`issm_nasd1987_new`, `issm_nasd1988`, `issm_nasd1988_new`, `issm_nasd1989`, `issm_nasd1989_new`, `issm_nasd1990`,
`issm_nasd1990_new`, `issm_nasd1991`, `issm_nasd1991_new`, `issm_nasd1992`, `issm_nasd1992_new`, `issm_nyam1983`,
`issm_nyam1983_new`, `issm_nyam1984`, `issm_nyam1984_new`, `issm_nyam1985`, `issm_nyam1985_new`, `issm_nyam1986`,
`issm_nyam1986_new`, `issm_nyam1987`, `issm_nyam1987_new`, `issm_nyam1988`, `issm_nyam1988_new`, `issm_nyam1989`,
`issm_nyam1989_new`, `issm_nyam1990`, `issm_nyam1990_new`, `issm_nyam1991`, `issm_nyam1991_new`, `issm_nyam1992`,
`issm_nyam1992_new`, `kld_histall`, `lspd_daily`, `lspd_daily_old`, `lspd_monthly`, `lspd_monthly_old`,
`lspdsamp_all`, `markit_cds`, `markit_cds_new`, `markit_cds_old`, `markit_cdxcomps`, `markit_cdxcomps_old`,
`markit_cdxconst`, `markit_cdxconst_old`, `markit_itraxxascomps`, `markit_itraxxascomps_old`, `markit_itraxxasconst`,
`markit_itraxxasconst_old`, `markit_itraxxeucomps`, `markit_itraxxeucomps_old`, `markit_itraxxeuconst`,
`markit_itraxxeuconst_old`, `markit_itraxxsocomps`, `markit_itraxxsocomps_old`, `markit_itraxxsoconst`,
`markit_itraxxsoconst_old`, `markit_msf_analytics_bonds`, `markit_msf_analytics_bonds_new`,
`markit_msf_analytics_bonds_old`, `markit_msf_analytics_eqty_amer`, `markit_msf_analytics_eqty_amer_new`,
`markit_msf_analytics_eqty_amer_old`, `markit_msf_analytics_eqty_asia`, `markit_msf_analytics_eqty_asia_new`,
`markit_msf_analytics_eqty_asia_old`, `markit_msf_analytics_eqty_euro`, `markit_msf_analytics_eqty_euro_new`,
`markit_msf_analytics_eqty_euro_old`, `markit_msf_analytics_eqty_other`, `markit_msf_analytics_eqty_other_new`,
`markit_msf_analytics_eqty_other_old`, `markit_msf_inst_bonds`, `markit_msf_inst_bonds_new`,
`markit_msf_inst_bonds_old`, `markit_msf_inst_eqty_amer`, `markit_msf_inst_eqty_amer_new`,
`markit_msf_inst_eqty_amer_old`, `markit_msf_inst_eqty_asia`, `markit_msf_inst_eqty_asia_new`,
`markit_msf_inst_eqty_asia_old`, `markit_msf_inst_eqty_euro`, `markit_msf_inst_eqty_euro_new`,
`markit_msf_inst_eqty_euro_old`, `markit_msf_inst_eqty_other`, `markit_msf_inst_eqty_other_new`,
`markit_msf_inst_eqty_other_old`, `markit_red`, `markit_red_new`, `markit_red_old`, `mflinks_all`, `mflinks_all_old`,
`morningstar_cisdm`, `morningstar_cisdm_old`, `mpsych_commodities`, `mpsych_commodities_old`, `mpsych_companies`,
`mpsych_companies_old`, `mpsych_crypto`, `mpsych_crypto_old`, `mpsych_currencies`, `mpsych_currencies_old`,
`mpsych_esg_companies`, `mpsych_esg_companies_old`, `mpsych_esg_countries`, `mpsych_esg_countries_old`,
`mpsych_locations`, `mpsych_locations_old`, `mpsych_sample_old`, `mpsych_sectors`, `mpsych_sectors_old`,
`mrktsamp_cds_old`, `mrktsamp_cdx_old`, `mrktsamp_msf_old`, `mrktsamp_red_old`, `msci_climate`, `msci_climate_old`,
`msci_climate_samp_old`, `msci_common`, `msci_common_old`, `msci_common_samp_old`, `msci_esg`, `msci_esg_old`,
`msci_esg_samp_old`, `msrb_all_old`, `nastraq_1999`, `nastraq_2000`, `nastraq_2001`,
`niq_product_attr_artificial_food`, `niq_product_attr_artificial_food_old`, `niq_product_attr_better_for_seg`,
`niq_product_attr_better_for_seg_old`, `niq_product_attr_clean_label`, `niq_product_attr_clean_label_old`,
`niq_product_attr_esg`, `niq_product_attr_esg_old`, `niq_rsd_alcohol`, `niq_rsd_alcohol_old`, `niq_rsd_food_bev`,
`niq_rsd_food_bev_old`, `niq_rsd_personal_care`, `niq_rsd_personal_care_old`, `niq_rsd_pet_care`,
`niq_rsd_pet_care_old`, `niq_rsd_tobacco`, `niq_rsd_tobacco_old`, `niq_samp_old`, `optionm_all`, `optionm_all_old`,
`optionm_europe`, `otc_endofday_old`, `pacap_all`, `pacap_indonesia`, `pacap_japan`, `pacap_korea`, `pacap_malaysia`,
`pacap_singapore`, `pacap_taiwan`, `panjiva`, `panjiva_old`, `panjiva_samp_old`, `permstub_all`, `permstub_all_old`,
`pg_catalog`, `pg_temp_0`, `pg_temp_101`, `pg_temp_104`, `pg_temp_108`, `pg_temp_110`, `pg_temp_112`, `pg_temp_113`,
`pg_temp_114`, `pg_temp_118`, `pg_temp_123`, `pg_temp_124`, `pg_temp_126`, `pg_temp_130`, `pg_temp_131`,
`pg_temp_134`, `pg_temp_137`, `pg_temp_141`, `pg_temp_142`, `pg_temp_143`, `pg_temp_146`, `pg_temp_15`,
`pg_temp_151`, `pg_temp_152`, `pg_temp_154`, `pg_temp_157`, `pg_temp_159`, `pg_temp_160`, `pg_temp_162`,
`pg_temp_165`, `pg_temp_168`, `pg_temp_169`, `pg_temp_172`, `pg_temp_173`, `pg_temp_176`, `pg_temp_182`,
`pg_temp_184`, `pg_temp_185`, `pg_temp_187`, `pg_temp_189`, `pg_temp_19`, `pg_temp_191`, `pg_temp_193`,
`pg_temp_203`, `pg_temp_210`, `pg_temp_212`, `pg_temp_213`, `pg_temp_215`, `pg_temp_216`, `pg_temp_217`,
`pg_temp_218`, `pg_temp_222`, `pg_temp_224`, `pg_temp_228`, `pg_temp_229`, `pg_temp_23`, `pg_temp_230`,
`pg_temp_231`, `pg_temp_238`, `pg_temp_239`, `pg_temp_24`, `pg_temp_241`, `pg_temp_242`, `pg_temp_244`,
`pg_temp_248`, `pg_temp_249`, `pg_temp_251`, `pg_temp_252`, `pg_temp_255`, `pg_temp_257`, `pg_temp_260`,
`pg_temp_262`, `pg_temp_265`, `pg_temp_266`, `pg_temp_267`, `pg_temp_27`, `pg_temp_270`, `pg_temp_276`,
`pg_temp_277`, `pg_temp_278`, `pg_temp_28`, `pg_temp_281`, `pg_temp_282`, `pg_temp_284`, `pg_temp_285`,
`pg_temp_287`, `pg_temp_295`, `pg_temp_3`, `pg_temp_303`, `pg_temp_306`, `pg_temp_307`, `pg_temp_308`, `pg_temp_310`,
`pg_temp_313`, `pg_temp_316`, `pg_temp_32`, `pg_temp_320`, `pg_temp_321`, `pg_temp_323`, `pg_temp_328`,
`pg_temp_333`, `pg_temp_334`, `pg_temp_336`, `pg_temp_34`, `pg_temp_340`, `pg_temp_341`, `pg_temp_344`,
`pg_temp_345`, `pg_temp_348`, `pg_temp_35`, `pg_temp_352`, `pg_temp_353`, `pg_temp_355`, `pg_temp_356`,
`pg_temp_358`, `pg_temp_36`, `pg_temp_360`, `pg_temp_361`, `pg_temp_365`, `pg_temp_37`, `pg_temp_370`, `pg_temp_372`,
`pg_temp_373`, `pg_temp_375`, `pg_temp_376`, `pg_temp_377`, `pg_temp_378`, `pg_temp_379`, `pg_temp_386`,
`pg_temp_39`, `pg_temp_391`, `pg_temp_392`, `pg_temp_393`, `pg_temp_4`, `pg_temp_407`, `pg_temp_409`, `pg_temp_410`,
`pg_temp_411`, `pg_temp_414`, `pg_temp_419`, `pg_temp_422`, `pg_temp_424`, `pg_temp_426`, `pg_temp_427`,
`pg_temp_428`, `pg_temp_432`, `pg_temp_433`, `pg_temp_434`, `pg_temp_440`, `pg_temp_441`, `pg_temp_444`,
`pg_temp_446`, `pg_temp_447`, `pg_temp_45`, `pg_temp_450`, `pg_temp_455`, `pg_temp_456`, `pg_temp_457`, `pg_temp_46`,
`pg_temp_461`, `pg_temp_462`, `pg_temp_466`, `pg_temp_467`, `pg_temp_468`, `pg_temp_471`, `pg_temp_472`,
`pg_temp_477`, `pg_temp_479`, `pg_temp_48`, `pg_temp_483`, `pg_temp_486`, `pg_temp_49`, `pg_temp_490`, `pg_temp_496`,
`pg_temp_497`, `pg_temp_499`, `pg_temp_502`, `pg_temp_506`, `pg_temp_508`, `pg_temp_510`, `pg_temp_511`,
`pg_temp_513`, `pg_temp_515`, `pg_temp_52`, `pg_temp_520`, `pg_temp_521`, `pg_temp_523`, `pg_temp_527`,
`pg_temp_531`, `pg_temp_533`, `pg_temp_537`, `pg_temp_539`, `pg_temp_54`, `pg_temp_540`, `pg_temp_542`,
`pg_temp_546`, `pg_temp_550`, `pg_temp_56`, `pg_temp_560`, `pg_temp_561`, `pg_temp_564`, `pg_temp_565`,
`pg_temp_566`, `pg_temp_568`, `pg_temp_57`, `pg_temp_571`, `pg_temp_573`, `pg_temp_574`, `pg_temp_576`,
`pg_temp_578`, `pg_temp_58`, `pg_temp_581`, `pg_temp_589`, `pg_temp_59`, `pg_temp_592`, `pg_temp_595`, `pg_temp_597`,
`pg_temp_604`, `pg_temp_605`, `pg_temp_606`, `pg_temp_610`, `pg_temp_611`, `pg_temp_613`, `pg_temp_615`,
`pg_temp_618`, `pg_temp_619`, `pg_temp_620`, `pg_temp_622`, `pg_temp_623`, `pg_temp_624`, `pg_temp_625`,
`pg_temp_630`, `pg_temp_632`, `pg_temp_633`, `pg_temp_639`, `pg_temp_642`, `pg_temp_645`, `pg_temp_646`,
`pg_temp_647`, `pg_temp_648`, `pg_temp_653`, `pg_temp_654`, `pg_temp_656`, `pg_temp_659`, `pg_temp_660`,
`pg_temp_662`, `pg_temp_664`, `pg_temp_665`, `pg_temp_669`, `pg_temp_67`, `pg_temp_670`, `pg_temp_671`,
`pg_temp_673`, `pg_temp_675`, `pg_temp_676`, `pg_temp_68`, `pg_temp_680`, `pg_temp_682`, `pg_temp_686`,
`pg_temp_692`, `pg_temp_696`, `pg_temp_697`, `pg_temp_699`, `pg_temp_7`, `pg_temp_70`, `pg_temp_700`, `pg_temp_701`,
`pg_temp_706`, `pg_temp_709`, `pg_temp_71`, `pg_temp_710`, `pg_temp_712`, `pg_temp_713`, `pg_temp_714`,
`pg_temp_716`, `pg_temp_717`, `pg_temp_721`, `pg_temp_73`, `pg_temp_733`, `pg_temp_735`, `pg_temp_741`,
`pg_temp_744`, `pg_temp_747`, `pg_temp_752`, `pg_temp_753`, `pg_temp_756`, `pg_temp_759`, `pg_temp_76`,
`pg_temp_761`, `pg_temp_762`, `pg_temp_763`, `pg_temp_765`, `pg_temp_768`, `pg_temp_769`, `pg_temp_77`,
`pg_temp_774`, `pg_temp_775`, `pg_temp_776`, `pg_temp_778`, `pg_temp_784`, `pg_temp_79`, `pg_temp_795`,
`pg_temp_796`, `pg_temp_797`, `pg_temp_799`, `pg_temp_8`, `pg_temp_80`, `pg_temp_82`, `pg_temp_83`, `pg_temp_9`,
`pg_temp_91`, `pg_temp_96`, `pg_temp_99`, `pg_toast`, `pg_toast_temp_0`, `pg_toast_temp_101`, `pg_toast_temp_104`,
`pg_toast_temp_108`, `pg_toast_temp_110`, `pg_toast_temp_112`, `pg_toast_temp_113`, `pg_toast_temp_114`,
`pg_toast_temp_118`, `pg_toast_temp_123`, `pg_toast_temp_124`, `pg_toast_temp_126`, `pg_toast_temp_130`,
`pg_toast_temp_131`, `pg_toast_temp_134`, `pg_toast_temp_137`, `pg_toast_temp_141`, `pg_toast_temp_142`,
`pg_toast_temp_143`, `pg_toast_temp_146`, `pg_toast_temp_15`, `pg_toast_temp_151`, `pg_toast_temp_152`,
`pg_toast_temp_154`, `pg_toast_temp_157`, `pg_toast_temp_159`, `pg_toast_temp_160`, `pg_toast_temp_162`,
`pg_toast_temp_165`, `pg_toast_temp_168`, `pg_toast_temp_169`, `pg_toast_temp_172`, `pg_toast_temp_173`,
`pg_toast_temp_176`, `pg_toast_temp_182`, `pg_toast_temp_184`, `pg_toast_temp_185`, `pg_toast_temp_187`,
`pg_toast_temp_189`, `pg_toast_temp_19`, `pg_toast_temp_191`, `pg_toast_temp_193`, `pg_toast_temp_203`,
`pg_toast_temp_210`, `pg_toast_temp_212`, `pg_toast_temp_213`, `pg_toast_temp_215`, `pg_toast_temp_216`,
`pg_toast_temp_217`, `pg_toast_temp_218`, `pg_toast_temp_222`, `pg_toast_temp_224`, `pg_toast_temp_228`,
`pg_toast_temp_229`, `pg_toast_temp_23`, `pg_toast_temp_230`, `pg_toast_temp_231`, `pg_toast_temp_238`,
`pg_toast_temp_239`, `pg_toast_temp_24`, `pg_toast_temp_241`, `pg_toast_temp_242`, `pg_toast_temp_244`,
`pg_toast_temp_248`, `pg_toast_temp_249`, `pg_toast_temp_251`, `pg_toast_temp_252`, `pg_toast_temp_255`,
`pg_toast_temp_257`, `pg_toast_temp_260`, `pg_toast_temp_262`, `pg_toast_temp_265`, `pg_toast_temp_266`,
`pg_toast_temp_267`, `pg_toast_temp_27`, `pg_toast_temp_270`, `pg_toast_temp_276`, `pg_toast_temp_277`,
`pg_toast_temp_278`, `pg_toast_temp_28`, `pg_toast_temp_281`, `pg_toast_temp_282`, `pg_toast_temp_284`,
`pg_toast_temp_285`, `pg_toast_temp_287`, `pg_toast_temp_295`, `pg_toast_temp_3`, `pg_toast_temp_303`,
`pg_toast_temp_306`, `pg_toast_temp_307`, `pg_toast_temp_308`, `pg_toast_temp_310`, `pg_toast_temp_313`,
`pg_toast_temp_316`, `pg_toast_temp_32`, `pg_toast_temp_320`, `pg_toast_temp_321`, `pg_toast_temp_323`,
`pg_toast_temp_328`, `pg_toast_temp_333`, `pg_toast_temp_334`, `pg_toast_temp_336`, `pg_toast_temp_34`,
`pg_toast_temp_340`, `pg_toast_temp_341`, `pg_toast_temp_344`, `pg_toast_temp_345`, `pg_toast_temp_348`,
`pg_toast_temp_35`, `pg_toast_temp_352`, `pg_toast_temp_353`, `pg_toast_temp_355`, `pg_toast_temp_356`,
`pg_toast_temp_358`, `pg_toast_temp_36`, `pg_toast_temp_360`, `pg_toast_temp_361`, `pg_toast_temp_365`,
`pg_toast_temp_37`, `pg_toast_temp_370`, `pg_toast_temp_372`, `pg_toast_temp_373`, `pg_toast_temp_375`,
`pg_toast_temp_376`, `pg_toast_temp_377`, `pg_toast_temp_378`, `pg_toast_temp_379`, `pg_toast_temp_386`,
`pg_toast_temp_39`, `pg_toast_temp_391`, `pg_toast_temp_392`, `pg_toast_temp_393`, `pg_toast_temp_4`,
`pg_toast_temp_407`, `pg_toast_temp_409`, `pg_toast_temp_410`, `pg_toast_temp_411`, `pg_toast_temp_414`,
`pg_toast_temp_419`, `pg_toast_temp_422`, `pg_toast_temp_424`, `pg_toast_temp_426`, `pg_toast_temp_427`,
`pg_toast_temp_428`, `pg_toast_temp_432`, `pg_toast_temp_433`, `pg_toast_temp_434`, `pg_toast_temp_440`,
`pg_toast_temp_441`, `pg_toast_temp_444`, `pg_toast_temp_446`, `pg_toast_temp_447`, `pg_toast_temp_45`,
`pg_toast_temp_450`, `pg_toast_temp_455`, `pg_toast_temp_456`, `pg_toast_temp_457`, `pg_toast_temp_46`,
`pg_toast_temp_461`, `pg_toast_temp_462`, `pg_toast_temp_466`, `pg_toast_temp_467`, `pg_toast_temp_468`,
`pg_toast_temp_471`, `pg_toast_temp_472`, `pg_toast_temp_477`, `pg_toast_temp_479`, `pg_toast_temp_48`,
`pg_toast_temp_483`, `pg_toast_temp_486`, `pg_toast_temp_49`, `pg_toast_temp_490`, `pg_toast_temp_496`,
`pg_toast_temp_497`, `pg_toast_temp_499`, `pg_toast_temp_502`, `pg_toast_temp_506`, `pg_toast_temp_508`,
`pg_toast_temp_510`, `pg_toast_temp_511`, `pg_toast_temp_513`, `pg_toast_temp_515`, `pg_toast_temp_52`,
`pg_toast_temp_520`, `pg_toast_temp_521`, `pg_toast_temp_523`, `pg_toast_temp_527`, `pg_toast_temp_531`,
`pg_toast_temp_533`, `pg_toast_temp_537`, `pg_toast_temp_539`, `pg_toast_temp_54`, `pg_toast_temp_540`,
`pg_toast_temp_542`, `pg_toast_temp_546`, `pg_toast_temp_550`, `pg_toast_temp_56`, `pg_toast_temp_560`,
`pg_toast_temp_561`, `pg_toast_temp_564`, `pg_toast_temp_565`, `pg_toast_temp_566`, `pg_toast_temp_568`,
`pg_toast_temp_57`, `pg_toast_temp_571`, `pg_toast_temp_573`, `pg_toast_temp_574`, `pg_toast_temp_576`,
`pg_toast_temp_578`, `pg_toast_temp_58`, `pg_toast_temp_581`, `pg_toast_temp_589`, `pg_toast_temp_59`,
`pg_toast_temp_592`, `pg_toast_temp_595`, `pg_toast_temp_597`, `pg_toast_temp_604`, `pg_toast_temp_605`,
`pg_toast_temp_606`, `pg_toast_temp_610`, `pg_toast_temp_611`, `pg_toast_temp_613`, `pg_toast_temp_615`,
`pg_toast_temp_618`, `pg_toast_temp_619`, `pg_toast_temp_620`, `pg_toast_temp_622`, `pg_toast_temp_623`,
`pg_toast_temp_624`, `pg_toast_temp_625`, `pg_toast_temp_630`, `pg_toast_temp_632`, `pg_toast_temp_633`,
`pg_toast_temp_639`, `pg_toast_temp_642`, `pg_toast_temp_645`, `pg_toast_temp_646`, `pg_toast_temp_647`,
`pg_toast_temp_648`, `pg_toast_temp_653`, `pg_toast_temp_654`, `pg_toast_temp_656`, `pg_toast_temp_659`,
`pg_toast_temp_660`, `pg_toast_temp_662`, `pg_toast_temp_664`, `pg_toast_temp_665`, `pg_toast_temp_669`,
`pg_toast_temp_67`, `pg_toast_temp_670`, `pg_toast_temp_671`, `pg_toast_temp_673`, `pg_toast_temp_675`,
`pg_toast_temp_676`, `pg_toast_temp_68`, `pg_toast_temp_680`, `pg_toast_temp_682`, `pg_toast_temp_686`,
`pg_toast_temp_692`, `pg_toast_temp_696`, `pg_toast_temp_697`, `pg_toast_temp_699`, `pg_toast_temp_7`,
`pg_toast_temp_70`, `pg_toast_temp_700`, `pg_toast_temp_701`, `pg_toast_temp_706`, `pg_toast_temp_709`,
`pg_toast_temp_71`, `pg_toast_temp_710`, `pg_toast_temp_712`, `pg_toast_temp_713`, `pg_toast_temp_714`,
`pg_toast_temp_716`, `pg_toast_temp_717`, `pg_toast_temp_721`, `pg_toast_temp_73`, `pg_toast_temp_733`,
`pg_toast_temp_735`, `pg_toast_temp_741`, `pg_toast_temp_744`, `pg_toast_temp_747`, `pg_toast_temp_752`,
`pg_toast_temp_753`, `pg_toast_temp_756`, `pg_toast_temp_759`, `pg_toast_temp_76`, `pg_toast_temp_761`,
`pg_toast_temp_762`, `pg_toast_temp_763`, `pg_toast_temp_765`, `pg_toast_temp_768`, `pg_toast_temp_769`,
`pg_toast_temp_77`, `pg_toast_temp_774`, `pg_toast_temp_775`, `pg_toast_temp_776`, `pg_toast_temp_778`,
`pg_toast_temp_784`, `pg_toast_temp_79`, `pg_toast_temp_795`, `pg_toast_temp_796`, `pg_toast_temp_797`,
`pg_toast_temp_799`, `pg_toast_temp_8`, `pg_toast_temp_80`, `pg_toast_temp_82`, `pg_toast_temp_83`,
`pg_toast_temp_9`, `pg_toast_temp_91`, `pg_toast_temp_96`, `pg_toast_temp_99`, `pgaudit`, `pitchbk_common`,
`pitchbk_common_old`, `pitchbk_companies_deals`, `pitchbk_companies_deals_old`, `pitchbk_fund_returns`,
`pitchbk_fund_returns_old`, `pitchbk_investors_funds_lps`, `pitchbk_investors_funds_lps_old`, `pitchbk_other_na`,
`pitchbk_other_na_old`, `pitchbk_other_row`, `pitchbk_other_row_old`, `pitchbk_pe_na`, `pitchbk_pe_na_old`,
`pitchbk_pe_row`, `pitchbk_pe_row_old`, `pitchbk_people`, `pitchbk_people_old`, `pitchbk_vc_na`, `pitchbk_vc_na_old`,
`pitchbk_vc_row`, `pitchbk_vc_row_old`, `pitchsmp_old`, `preqin_cashflow`, `preqin_cashflow_old`, `preqin_deals`,
`preqin_deals_old`, `preqin_gp`, `preqin_gp_old`, `preqin_lp`, `preqin_lp_old`, `preqin_pe`, `preqin_vc`,
`public_all_new`, `ravenpack_common`, `ravenpack_common_old`, `ravenpack_dj`, `ravenpack_dj_new`, `ravenpack_dj_old`,
`ravenpack_full`, `ravenpack_full_new`, `ravenpack_full_old`, `ravenpack_pr_new`, `ravenpack_web`,
`ravenpack_web_new`, `ravenpack_web_old`, `reprisk_common`, `reprisk_pm`, `reprisk_std`, `reprisk_v2`,
`reprisk_v2_old`, `revelio_common`, `revelio_common_old`, `revelio_individual`, `revelio_individual_new`,
`revelio_individual_old`, `revelio_job_postings`, `revelio_job_postings_old`, `revelio_layoffs`,
`revelio_layoffs_old`, `revelio_samp_old`, `revelio_sentiment`, `revelio_sentiment_old`,
`revelio_workforce_dynamics`, `revelio_workforce_dynamics_old`, `risk_directors_new`, `risk_directors_old`,
`risk_governance`, `risk_governance_new`, `risk_governance_old`, `risk_proposals_new`, `risk_proposals_old`,
`risksamp_all_old`, `rpa1_0_dj_pr_editions`, `rpa1_0_dj_pr_editions_new`, `rpa1_0_full_edition`,
`rpa1_0_full_edition_new`, `rq_all_old`, `rstat_royalty`, `secsamp_all_old`, `sp_esg`, `sp_esg_old`, `spre_apac`,
`spre_apac_old`, `spre_emea`, `spre_emea_old`, `spre_latam`, `spre_latam_old`, `spre_na`, `spre_na_old`, `spre_usa`,
`spre_usa_old`, `sustainalytics_all`, `sustainalytics_all_old`, `sustainalyticssamp_all_old`, `taq_common`,
`taq_common_new`, `taqm_2003`, `taqm_2004`, `taqm_2005`, `taqm_2006`, `taqm_2007`, `taqm_2008`, `taqm_2009`,
`taqm_2009_new`, `taqm_2010`, `taqm_2011`, `taqm_2011_new`, `taqm_2012`, `taqm_2013`, `taqm_2014`, `taqm_2015`,
`taqm_2016`, `taqm_2017`, `taqm_2018`, `taqm_2019`, `taqm_2020`, `taqm_2021`, `taqm_2022`, `taqm_2023`,
`taqm_2023_new`, `taqm_2024`, `taqm_2025`, `taqm_2026`, `taqm_2026_new`, `taqm_2026_old`, `taqsamp_all_new`,
`test_new`, `tfn_common`, `tfn_common_new`, `totalq_all_old`, `tr_13f`, `tr_13f_new`, `tr_13f_old`, `tr_common`,
`tr_common_new`, `tr_common_old`, `tr_dandb_dmi_us`, `tr_dandb_dmi_us_new`, `tr_dandb_dmi_us_old`, `tr_dandb_wb_af`,
`tr_dandb_wb_af_new`, `tr_dandb_wb_af_old`, `tr_dandb_wb_ap`, `tr_dandb_wb_ap_new`, `tr_dandb_wb_ap_old`,
`tr_dandb_wb_eu`, `tr_dandb_wb_eu_new`, `tr_dandb_wb_eu_old`, `tr_dandb_wb_la`, `tr_dandb_wb_la_new`,
`tr_dandb_wb_la_old`, `tr_dandb_wb_me`, `tr_dandb_wb_me_new`, `tr_dandb_wb_me_old`, `tr_dandb_wb_na`,
`tr_dandb_wb_na_new`, `tr_dandb_wb_na_old`, `tr_dandb_wb_unknown`, `tr_dandb_wb_unknown_new`,
`tr_dandb_wb_unknown_old`, `tr_dealscan`, `tr_dealscan_old`, `tr_digital_assets`, `tr_digital_assets_old`,
`tr_ds_comds`, `tr_ds_comds_old`, `tr_ds_econ`, `tr_ds_econ_old`, `tr_ds_equities`, `tr_ds_equities_old`,
`tr_ds_fut`, `tr_ds_fut_old`, `tr_esg`, `tr_esg_old`, `tr_ibes`, `tr_ibes_corporate`, `tr_ibes_guidance`,
`tr_ibes_guidance_old`, `tr_ibes_iga`, `tr_ibes_iga_old`, `tr_ibes_old`, `tr_ibeskpi`, `tr_ibeskpi_old`,
`tr_insiders`, `tr_insiders_old`, `tr_mutualfunds`, `tr_mutualfunds_old`, `tr_ownership`, `tr_ownership_old`,
`tr_sdc_joint_ventures`, `tr_sdc_joint_ventures_old`, `tr_sdc_ma`, `tr_sdc_ma_old`, `tr_sdc_municipals`,
`tr_sdc_municipals_old`, `tr_sdc_ni`, `tr_sdc_ni_old`, `tr_sdc_private_equity`, `tr_sdc_private_equity_old`,
`tr_tass`, `tr_tass_old`, `tr_worldscope`, `tr_worldscope_old`, `trace_enhanced_old`, `trace_standard_old`,
`trsamp_da`, `trsamp_da_old`, `trucost_carbon`, `trucost_carbon_old`, `trucost_common`, `trucost_common_old`,
`trucost_environ`, `trucost_environ_old`, `trucost_fossilfuel`, `trucost_fossilfuel_old`, `trucost_paris`,
`trucost_paris_old`, `trucost_risk`, `trucost_risk_old`, `trucost_samp_old`, `trucost_sector`, `trucost_sector_ff`,
`trucost_sector_ff_old`, `trucost_sector_revenue`, `trucost_sector_revenue_old`, `twoiq_all`, `twoiq_all_old`,
`wharton_shared_data`, `wharton_shared_data_new`, `wind_ashare`, `wind_code`, `windsmp`, `wrds_abs`, `wrds_abs_old`,
`wrds_abs_samp_old`, `wrds_attribute_search`, `wrds_backtest`, `wrds_backtest_new`, `wrds_backtest_old`,
`wrds_environmental`, `wrds_environmental_old`, `wrds_environmental_samp_old`, `wrds_finra_short_interest`,
`wrds_finra_short_interest_old`, `wrds_insiders`, `wrds_insiders_new`, `wrds_insiders_old`, `wrds_insiders_samp_old`,
`wrds_internal`, `wrds_internal_new`, `wrds_internal_old`, `wrds_labs`, `wrds_metadata`, `wrds_mutualfund`,
`wrds_mutualfund_new`, `wrds_mutualfund_old`, `wrds_sec_search`, `wrds_short_volume`, `wrds_short_volume_old`,
`wrds_shortvolume_samp_old`, `wrds_text_analytics`, `wrds_trade_exec_samp`, `wrds_trade_exec_samp_old`,
`wrds_trade_execution`, `wrds_trade_execution_old`, `wrds_trading_suite`, `wrds_trading_suite_old`,
`wrds_xbrl_fundamental`, `wrds_xbrl_fundamental_old`, `wrdsapps_backtest_basic`, `wrdsapps_backtest_basic_old`,
`wrdsapps_backtest_plus`, `wrdsapps_backtest_plus_old`, `wrdsapps_bondret`, `wrdsapps_bondret_old`,
`wrdsapps_eushort_old`, `wrdsapps_evtint_new`, `wrdsapps_evtstudy_int_ginsight_new`,
`wrdsapps_evtstudy_intraday_rav`, `wrdsapps_evtstudy_intraday_rav_old`, `wrdsapps_evtstudy_lr`,
`wrdsapps_evtstudy_lr_ciq`, `wrdsapps_evtstudy_lr_ciq_old`, `wrdsapps_evtstudy_lr_old`, `wrdsapps_finratio_ccm`,
`wrdsapps_finratio_ccm_old`, `wrdsapps_finratio_ibes`, `wrdsapps_finratio_ibes_ccm`,
`wrdsapps_finratio_ibes_ccm_old`, `wrdsapps_finratio_ibes_old`, `wrdsapps_finratio_old`,
`wrdsapps_link_comp_eushort_old`, `wrdsapps_link_crsp_bond_old`, `wrdsapps_link_crsp_comp_bdx`,
`wrdsapps_link_crsp_comp_bdx_old`, `wrdsapps_link_crsp_factset_old`, `wrdsapps_link_crsp_ibes`,
`wrdsapps_link_crsp_ibes_old`, `wrdsapps_link_crsp_optionm`, `wrdsapps_link_crsp_optionm_old`,
`wrdsapps_link_crsp_taqm`, `wrdsapps_link_crsp_taqm_new`, `wrdsapps_link_crsp_taqm_old`,
`wrdsapps_link_datastream_wscope`, `wrdsapps_link_datastream_wscope_old`, `wrdsapps_link_dealscan_wscope`,
`wrdsapps_link_supplychain`, `wrdsapps_link_supplychain_old`, `wrdsapps_link_trinsider_bdx`,
`wrdsapps_link_trinsider_bdx_old`, `wrdsapps_plink_boardex_ciq`, `wrdsapps_plink_boardex_ciq_old`,
`wrdsapps_plink_boardex_trinsider`, `wrdsapps_plink_boardex_trinsider_old`, `wrdsapps_plink_boardex_twoiq`,
`wrdsapps_plink_boardex_twoiq_old`, `wrdsapps_plink_exec_boardex_old`, `wrdsapps_plink_exec_ciq`,
`wrdsapps_plink_exec_ciq_old`, `wrdsapps_plink_exec_trinsider`, `wrdsapps_plink_exec_trinsider_old`,
`wrdsapps_plink_exec_twoiq`, `wrdsapps_plink_exec_twoiq_old`, `wrdsapps_plink_trinsider_ciq`,
`wrdsapps_plink_trinsider_ciq_old`, `wrdsapps_plink_trinsider_twoiq`, `wrdsapps_plink_trinsider_twoiq_old`,
`wrdsapps_plink_twoiq_ciq`, `wrdsapps_plink_twoiq_ciq_old`, `wrdsapps_subsidiary_old`, `wrdsapps_windices_old`,
`wrdsapps_wlink_new`, `wrdssec_all`, `wrdssec_all_new`, `wrdssec_all_old`, `wrdssec_bow`, `wrdssec_bow_new`,
`wrdssec_bow_old`, `wrdssec_common`, `wrdssec_common_new`, `wrdssec_common_old`, `wrdssec_insiders`,
`wrdssec_insiders_new`, `wrdssec_midas_old`, `wrdssec_premium`, `wrdssec_premium_new`, `wrdssec_secsa`,
`wrdssec_secsa_new`, `wrdssec_secsa_old`, `wta_audit_audit_comp`, `wta_ciq_keydev`, `wta_ciq_transcripts`,
`wta_ciqsamp_keydev`, `wta_gutenberg`, `wta_lexisnexis_metabase`, `wta_twitter_samp`, `wta_wrdssec_all`, `zacks_all`,
`zacks_all_old`
