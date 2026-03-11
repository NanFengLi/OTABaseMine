/*
 *
 * Copyright 2021-2026 Software Radio Systems Limited
 *
 * This file is part of srsRAN.
 *
 * srsRAN is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version.
 *
 * srsRAN is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * A copy of the GNU Affero General Public License can be found in
 * the LICENSE file in the top-level directory of this distribution
 * and at http://www.gnu.org/licenses/.
 *
 */

#include "rrc_ue_helpers.h"
#include "rrc_ue_impl.h"
#include "srsran/asn1/rrc_nr/dl_ccch_msg.h"
#include "srsran/asn1/rrc_nr/dl_dcch_msg.h"
#include <cstdlib>
#include <fstream>
#include <sstream>

using namespace srsran;
using namespace srs_cu_cp;
using namespace asn1::rrc_nr;

void rrc_ue_impl::send_dl_ccch(const dl_ccch_msg_s& dl_ccch_msg)
{
  // Pack DL CCCH msg.
  byte_buffer pdu = pack_into_pdu(dl_ccch_msg, "DL-CCCH-Message");

  // Log Tx message
  log_rrc_message(logger, Tx, pdu, dl_ccch_msg, srb_id_t::srb0, "CCCH DL");

  // Send down the stack.
  logger.log_debug(pdu.begin(), pdu.end(), "Tx {} PDU", srb_id_t::srb0);
  f1ap_pdu_notifier.on_new_rrc_pdu(srb_id_t::srb0, std::move(pdu));
}

void rrc_ue_impl::send_dl_dcch(srb_id_t srb_id, const dl_dcch_msg_s& dl_dcch_msg)
{
  if (context.srbs.find(srb_id) == context.srbs.end()) {
    logger.log_error("Dropping DlDcchMessage. Tx {} is not set up", srb_id);
    return;
  }

  // Pack DL CCCH msg.
  byte_buffer pdu = pack_into_pdu(dl_dcch_msg, "DL-DCCH-Message");

  // Log Tx message.
  log_rrc_message(logger, Tx, pdu, dl_dcch_msg, srb_id, "DCCH DL");

  // Pack PDCP PDU and send down the stack.
  auto pdcp_packing_result = context.srbs.at(srb_id).pack_rrc_pdu(std::move(pdu));
  if (!pdcp_packing_result.is_successful()) {
    logger.log_info("Requesting UE release. Cause: PDCP packing failed with {}",
                    pdcp_packing_result.get_failure_cause());
    on_ue_release_required(pdcp_packing_result.get_failure_cause());
    return;
  }

  byte_buffer pdcp_pdu = pdcp_packing_result.pop_pdu();
  logger.log_debug(pdcp_pdu.begin(), pdcp_pdu.end(), "Tx {} PDU", context.ue_index, context.c_rnti, srb_id);
  f1ap_pdu_notifier.on_new_rrc_pdu(srb_id, std::move(pdcp_pdu));
}

bool rrc_ue_impl::send_dl_dcch_bytes(srb_id_t srb_id, const std::string& payload_hex)
{
  if (context.srbs.find(srb_id) == context.srbs.end()) {
    logger.log_error("Dropping OTABase payload. Tx {} is not set up", srb_id);
    return false;
  }

  std::vector<uint8_t> bytes;
  if (!decode_hex_payload(payload_hex, bytes)) {
    logger.log_error("Failed to decode OTABase payload hex (len={})", payload_hex.size());
    return false;
  }

  auto rrc_pdu = byte_buffer::create(span<const uint8_t>(bytes.data(), bytes.size()));
  if (!rrc_pdu.has_value()) {
    logger.log_error("Failed to allocate OTABase RRC PDU buffer");
    return false;
  }

  auto pdcp_packing_result = context.srbs.at(srb_id).pack_rrc_pdu(rrc_pdu.value());
  if (!pdcp_packing_result.is_successful()) {
    logger.log_info("Requesting UE release. Cause: PDCP packing failed with {}",
                    pdcp_packing_result.get_failure_cause());
    on_ue_release_required(pdcp_packing_result.get_failure_cause());
    return false;
  }

  byte_buffer pdcp_pdu = pdcp_packing_result.pop_pdu();
  logger.log_debug(pdcp_pdu.begin(), pdcp_pdu.end(), "Tx {} OTABase raw PDU", context.ue_index, context.c_rnti, srb_id);
  f1ap_pdu_notifier.on_new_rrc_pdu(srb_id, std::move(pdcp_pdu));
  return true;
}

void rrc_ue_impl::maybe_send_next_otabase_rrc_message(const char* trigger)
{
  if (!context.cfg.otabase_enable_5g_rrc_fuzzing || context.state != rrc_state::connected) {
    return;
  }

  std::string payload_hex;
  if (!get_otabase_test_msg_from_file(payload_hex)) {
    return;
  }

  logger.log_info("OTABase trigger={} send payload len={}B", trigger, payload_hex.size() / 2U);
  send_dl_dcch_bytes(srb_id_t::srb1, payload_hex);
}

bool rrc_ue_impl::get_otabase_test_msg_from_file(std::string& payload_hex)
{
  const std::string& index_file_name = context.cfg.otabase_test_index_file;

  if (!otabase_is_test_file_open) {
    std::ifstream index_file(index_file_name);
    if (!index_file.is_open()) {
      logger.log_warning("OTABase: failed to open index file {}", index_file_name);
      return false;
    }

    std::string index_line;
    if (!std::getline(index_file, index_line) || index_line.empty()) {
      logger.log_warning("OTABase: empty index file {}", index_file_name);
      return false;
    }

    std::istringstream index_stream(index_line);
    std::getline(index_stream, otabase_test_file_name, ',');
    if (otabase_test_file_name.empty()) {
      logger.log_warning("OTABase: invalid index file first token");
      return false;
    }

    otabase_cur_line_num  = 1;
    otabase_total_line_num = 0;

    if (!index_stream.eof()) {
      if (!(index_stream >> otabase_cur_line_num)) {
        otabase_cur_line_num = 1;
      }
      if (index_stream.peek() == ',') {
        index_stream.get();
      }
      if (!(index_stream >> otabase_total_line_num)) {
        otabase_total_line_num = 0;
      }
    }

    otabase_input_test_file.open(otabase_test_file_name);
    if (!otabase_input_test_file.is_open()) {
      logger.log_warning("OTABase: failed to open payload file {}", otabase_test_file_name);
      return false;
    }

    otabase_is_test_file_open = true;

    std::string first_line;
    if (!(otabase_input_test_file >> otabase_total_line_num)) {
      logger.log_warning("OTABase: failed to read payload count in {}", otabase_test_file_name);
      return false;
    }
    std::getline(otabase_input_test_file, first_line);

    for (unsigned i = 1; i < otabase_cur_line_num; ++i) {
      if (!std::getline(otabase_input_test_file, first_line)) {
        break;
      }
    }
  }

  std::string line;
  if (!std::getline(otabase_input_test_file, line)) {
    const std::string next_file = increment_otabase_filename(otabase_test_file_name);

    std::ofstream index_file(index_file_name);
    if (index_file.is_open()) {
      index_file << next_file << '\n';
    }

    otabase_input_test_file.close();
    otabase_is_test_file_open = false;
    otabase_test_file_name.clear();
    otabase_cur_line_num   = 1;
    otabase_total_line_num = 0;

    return get_otabase_test_msg_from_file(payload_hex);
  }

  ++otabase_cur_line_num;

  std::ofstream index_file(index_file_name);
  if (index_file.is_open()) {
    index_file << otabase_test_file_name << ',' << otabase_cur_line_num << ',' << otabase_total_line_num << '\n';
  }

  std::istringstream line_stream(line);
  std::string        numbering;
  std::string        msg_name;
  std::string        field_name;
  std::getline(line_stream, numbering, ',');
  std::getline(line_stream, payload_hex, ',');
  std::getline(line_stream, msg_name, ',');
  std::getline(line_stream, field_name);

  if (payload_hex.empty()) {
    logger.log_warning("OTABase: empty payload at {}:{}", otabase_test_file_name, otabase_cur_line_num - 1);
    return false;
  }

  return true;
}

bool rrc_ue_impl::decode_hex_payload(const std::string& payload_hex, std::vector<uint8_t>& out_bytes)
{
  out_bytes.clear();
  std::string input = payload_hex;

  if ((input.size() % 2U) != 0U) {
    input.push_back('0');
  }

  out_bytes.reserve(input.size() / 2U);
  for (size_t i = 0; i < input.size(); i += 2) {
    const std::string byte_str = input.substr(i, 2);
    char*             end_ptr  = nullptr;
    long              value    = std::strtol(byte_str.c_str(), &end_ptr, 16);
    if (end_ptr == nullptr || *end_ptr != '\0' || value < 0 || value > 255) {
      return false;
    }
    out_bytes.push_back(static_cast<uint8_t>(value));
  }
  return true;
}

std::string rrc_ue_impl::increment_otabase_filename(const std::string& filename)
{
  const size_t pos = filename.find_first_of("0123456789");
  if (pos == std::string::npos) {
    return filename;
  }
  const std::string prefix  = filename.substr(0, pos);
  const std::string num_str = filename.substr(pos);
  return prefix + std::to_string(std::stoi(num_str) + 1);
}
