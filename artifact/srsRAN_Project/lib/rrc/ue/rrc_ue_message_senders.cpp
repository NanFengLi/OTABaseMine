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
#include "procedures/rrc_ue_capability_transfer_procedure.h"
#include "srsran/asn1/rrc_nr/dl_ccch_msg.h"
#include "srsran/asn1/rrc_nr/dl_dcch_msg.h"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
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

  auto pdcp_packing_result = context.srbs.at(srb_id).pack_rrc_pdu(std::move(rrc_pdu.value()));
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

  // If we are waiting for an oracle response, do nothing — the handler will resume.
  if (otabase_waiting_for_rrc_oracle) {
    return;
  }

  // Dispatch: backtracking mode vs normal testing.
  if (otabase_is_backtracking && !context.cfg.otabase_replay_mode) {
    send_rrc_test_message_backtracking();
    return;
  }

  // Increment oracle counter.
  otabase_num_msg_N_oracle++;

  // In replay mode, use a shorter check period.
  unsigned effective_check_period = context.cfg.otabase_check_period;
  if (context.cfg.otabase_replay_mode) {
    effective_check_period = 2;
  }

  // Periodically send UECapabilityEnquiry as an oracle liveness check.
  if (otabase_num_msg_N_oracle % effective_check_period == 0) {
    send_ue_cap_enquiry_oracle();
    return;
  }

  // Otherwise, send the next test message from file.
  std::string payload_hex;
  if (!get_otabase_test_msg_from_file(payload_hex)) {
    return;
  }

  logger.log_info("OTABase trigger={} send payload len={}B", trigger, payload_hex.size() / 2U);
  send_dl_dcch_bytes(srb_id_t::srb1, payload_hex);
}

bool rrc_ue_impl::get_otabase_test_msg_from_file(std::string& payload_hex)
{
  static const std::string index_file_name = "testFileIndex";

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

  // Check temporary blacklist — skip if this msg+field is currently blacklisted.
  if (!msg_name.empty() && !field_name.empty()) {
    std::string key = msg_name + "," + field_name;
    if (std::find(otabase_blacklist_active.begin(), otabase_blacklist_active.end(), key) !=
        otabase_blacklist_active.end()) {
      logger.log_info("OTABase: skipping blacklisted {}", key);
      return get_otabase_test_msg_from_file(payload_hex);
    }
  }

  // Enqueue for backtracking: "payload,msgName,fieldName".
  if (!msg_name.empty()) {
    std::string queue_entry = payload_hex + "," + msg_name + "," + field_name;
    put_otabase_test_message_queue(queue_entry);
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

// ---------------------------------------------------------------------------
// OTABase Oracle — send UECapabilityEnquiry as liveness check
// ---------------------------------------------------------------------------
void rrc_ue_impl::send_ue_cap_enquiry_oracle()
{
  using namespace asn1::rrc_nr;

  dl_dcch_msg_s dl_dcch_msg;
  dl_dcch_msg.msg.set_c1().set_ue_cap_enquiry();

  ue_cap_enquiry_s& enquiry = dl_dcch_msg.msg.c1().ue_cap_enquiry();
  fill_asn1_rrc_ue_capability_enquiry(enquiry, 0, context.cell.bands);

  otabase_waiting_for_rrc_oracle = true;
  set_otabase_oracle_timer();

  logger.log_info("OTABase: sending RRC liveness check (UECapabilityEnquiry)");
  send_dl_dcch(srb_id_t::srb1, dl_dcch_msg);
}

void rrc_ue_impl::set_otabase_oracle_timer()
{
  if (!otabase_oracle_timer.is_valid()) {
    otabase_oracle_timer = cu_cp_ue_notifier.get_timer_factory().create_timer();
  }

  otabase_oracle_timer.set(std::chrono::milliseconds(1000),
                           [this](timer_id_t tid) { otabase_oracle_timer_expired(tid); });
  otabase_oracle_timer.run();
  logger.log_info("OTABase: oracle timer started (1000ms)");
}

void rrc_ue_impl::otabase_oracle_timer_expired(timer_id_t /*tid*/)
{
  logger.log_info("OTABase: oracle timer expired — UE did not respond");
  otabase_oracle_timer.stop();
  otabase_waiting_for_rrc_oracle = false;
  notify_rrc_oracle();
}

// ---------------------------------------------------------------------------
// notify_rrc_oracle — called when UE fails to respond to liveness check
// ---------------------------------------------------------------------------
void rrc_ue_impl::notify_rrc_oracle()
{
  otabase_rrc_oracle_cnt++;
  constexpr uint8_t max_oracle_trial = 2;

  if (otabase_rrc_oracle_cnt > max_oracle_trial) {
    if (!otabase_is_backtracking) {
      // Enter backtracking mode.
      otabase_is_backtracking        = true;
      otabase_backtracking_num       = 0;
      otabase_backtracking_num_total = 0;
      otabase_backtracking_msg.clear();
      logger.log_info("OTABase: entering backtracking mode");
    } else {
      // Oracle failed during backtracking — we found a crash candidate.
      if (otabase_backtracking_num == 1) {
        logger.log_info("OTABase: found best crash candidate");
        save_otabase_recent_messages(otabase_backtracking_msg);
      } else {
        logger.log_info("OTABase: found candidate at backtracking position {}", otabase_backtracking_num);
        save_otabase_recent_messages(otabase_backtracking_msg,
                                     static_cast<int>(otabase_backtracking_num));
      }
      if (!context.cfg.otabase_replay_mode) {
        otabase_blacklist_test_cases(otabase_backtracking_msg);
        otabase_temp_blacklist_test_cases(otabase_backtracking_msg);
      }
    }
  } else {
    // Retry oracle — send UECapabilityEnquiry again.
    send_ue_cap_enquiry_oracle();
    logger.log_info("OTABase: oracle retry #{}", otabase_rrc_oracle_cnt);
  }
}

// ---------------------------------------------------------------------------
// Backtracking — replay recent messages to find the crash candidate
// ---------------------------------------------------------------------------
void rrc_ue_impl::send_rrc_test_message_backtracking()
{
  std::vector<std::string> backtracking_queue = get_otabase_recent_messages();

  otabase_backtracking_num++;
  otabase_backtracking_num_total++;

  // Check if backtracking is done (exhausted all messages).
  if (otabase_backtracking_num > backtracking_queue.size()) {
    logger.log_info("OTABase: backtracking done — no candidate isolated");
    otabase_is_backtracking        = false;
    otabase_backtracking_num       = 0;
    otabase_backtracking_num_total = 0;
    otabase_backtracking_msg.clear();
    // Clear queue so we don't replay old messages.
    otabase_test_msg_queue = {};
    // Resume normal testing.
    maybe_send_next_otabase_rrc_message("backtracking_done");
    return;
  }

  // Alternate: even iterations send oracle check, odd iterations send test payload.
  if (otabase_backtracking_num_total % 2 == 0) {
    otabase_backtracking_num--;
    logger.log_info("OTABase: backtracking oracle check #{}", otabase_backtracking_num_total / 2);
    send_ue_cap_enquiry_oracle();
    return;
  }

  // Send the backtracking payload (newest first).
  size_t idx = backtracking_queue.size() - static_cast<size_t>(otabase_backtracking_num);
  const std::string& payload_msg_path = backtracking_queue[idx];
  otabase_backtracking_msg = payload_msg_path;

  // Extract payload (first comma-separated field).
  std::string payload;
  {
    std::istringstream iss(payload_msg_path);
    std::getline(iss, payload, ',');
  }

  logger.log_info("OTABase: [Backtracking #{}] payload len={}B", otabase_backtracking_num, payload.size() / 2U);
  send_dl_dcch_bytes(srb_id_t::srb1, payload);
}

// ---------------------------------------------------------------------------
// Test message queue — FIFO of recent test messages for backtracking
// ---------------------------------------------------------------------------
void rrc_ue_impl::put_otabase_test_message_queue(const std::string& test_message)
{
  otabase_test_msg_queue.push(test_message);
  while (otabase_test_msg_queue.size() > otabase_queue_max_size) {
    otabase_test_msg_queue.pop();
  }
}

std::vector<std::string> rrc_ue_impl::get_otabase_recent_messages()
{
  std::vector<std::string> recent;
  std::queue<std::string>  temp = otabase_test_msg_queue;
  while (!temp.empty()) {
    recent.push_back(temp.front());
    temp.pop();
  }
  if (recent.size() > 10) {
    recent.erase(recent.begin(), recent.end() - 10);
  }
  return recent;
}

// ---------------------------------------------------------------------------
// save_otabase_recent_messages — persist crash candidates to disk
// ---------------------------------------------------------------------------
void rrc_ue_impl::save_otabase_recent_messages(const std::string& candidate, int order)
{
  namespace fs = std::filesystem;

  const std::string log_dir = "otabase_crashes";
  fs::create_directories(log_dir + "/crashes");

  // Keep a persistent crash counter to match OTABase behavior across restarts.
  const std::string crash_count_file = log_dir + "/crashes/crash_count.txt";
  if (otabase_crash_counter == 0 && fs::exists(crash_count_file)) {
    std::ifstream in_count(crash_count_file);
    if (in_count.is_open()) {
      in_count >> otabase_crash_counter;
    }
  }
  ++otabase_crash_counter;

  // Build JSON-like plain-text report of the recent messages.
  std::ostringstream report;
  report << "{\n";
  std::queue<std::string> temp = otabase_test_msg_queue;
  int idx = 0;
  while (!temp.empty()) {
    const std::string& entry = temp.front();
    std::istringstream iss(entry);
    std::string payload, msg_name, field_name;
    std::getline(iss, payload, ',');
    std::getline(iss, msg_name, ',');
    std::getline(iss, field_name);
    report << "  \"" << idx << "\": {\"Payload\": \"" << payload
           << "\", \"Message\": \"" << msg_name
           << "\", \"Field\": \"" << field_name << "\"}";
    temp.pop();
    if (!temp.empty()) {
      report << ",";
    }
    report << "\n";
    ++idx;
  }

  if (!candidate.empty()) {
    std::istringstream iss(candidate);
    std::string c_payload, c_msg, c_field;
    std::getline(iss, c_payload, ',');
    std::getline(iss, c_msg, ',');
    std::getline(iss, c_field);
    std::string label = (order == 0) ? "Best Candidate" : "Candidate " + std::to_string(order);
    report << "  ,\"" << label << "\": {\"Payload\": \"" << c_payload
           << "\", \"Message\": \"" << c_msg
           << "\", \"Field\": \"" << c_field << "\"}\n";
  }
  report << "}\n";

  std::string crash_dir = log_dir + "/crashes/crash_" + std::to_string(otabase_crash_counter);
  while (fs::exists(crash_dir)) {
    ++otabase_crash_counter;
    crash_dir = log_dir + "/crashes/crash_" + std::to_string(otabase_crash_counter);
  }
  fs::create_directories(crash_dir);

  std::ofstream out_count(crash_count_file);
  if (out_count.is_open()) {
    out_count << otabase_crash_counter;
  }

  const std::string candidate_list_file = log_dir + "/candidate_list.txt";
  std::ofstream      out_candidate(candidate_list_file, std::ios::app);
  if (out_candidate.is_open()) {
    const uint64_t candidate_line = otabase_cur_line_num - otabase_backtracking_num;
    out_candidate << otabase_test_file_name << "," << candidate_line << "\n";
  }

  std::ofstream out(crash_dir + "/candidates.json");
  if (out.is_open()) {
    out << report.str();
    out.close();
    logger.log_info("OTABase: saved crash candidates to {}", crash_dir);
  }
}

// ---------------------------------------------------------------------------
// Blacklisting — permanent (skip ahead in file) and temporary
// ---------------------------------------------------------------------------
void rrc_ue_impl::otabase_blacklist_test_cases(const std::string& blacklist_msg)
{
  // Extract msgName + fieldName from "payload,msgName,fieldName".
  std::istringstream iss(blacklist_msg);
  std::string        payload, msg_and_fields;
  std::getline(iss, payload, ',');
  std::getline(iss, msg_and_fields);

  if (msg_and_fields.empty()) {
    return;
  }

  // Skip ahead in the input file past all entries with the same msgName+fieldName.
  std::string line;
  while (true) {
    std::streampos cur_pos = otabase_input_test_file.tellg();
    if (!std::getline(otabase_input_test_file, line)) {
      break;
    }

    otabase_cur_line_num++;
    std::istringstream ls(line);
    std::string        num, pl, cur_msg_fields;
    std::getline(ls, num, ',');
    std::getline(ls, pl, ',');
    std::getline(ls, cur_msg_fields);

    if (cur_msg_fields != msg_and_fields) {
      // Went past the blacklisted block — roll back so this line is read next time.
      otabase_input_test_file.clear();
      otabase_input_test_file.seekg(cur_pos);
      otabase_cur_line_num--;
      break;
    }
    logger.log_info("OTABase: blacklist skip line {}", otabase_cur_line_num - 1);
  }
}

void rrc_ue_impl::otabase_temp_blacklist_test_cases(const std::string& blacklist_msg)
{
  std::istringstream iss(blacklist_msg);
  std::string        payload, msg_and_fields;
  std::getline(iss, payload, ',');
  std::getline(iss, msg_and_fields);

  if (msg_and_fields.empty()) {
    return;
  }

  otabase_blacklist_count[msg_and_fields]++;

  if (otabase_blacklist_count[msg_and_fields] == otabase_blacklist_max_count) {
    if (std::find(otabase_blacklist_active.begin(), otabase_blacklist_active.end(), msg_and_fields) ==
        otabase_blacklist_active.end()) {
      otabase_blacklist_active.push_back(msg_and_fields);
      logger.log_info("OTABase: temp-blacklisted {}", msg_and_fields);
    }
  }

  if (otabase_blacklist_count[msg_and_fields] >= otabase_blacklist_reset_threshold) {
    otabase_blacklist_count[msg_and_fields] = 0;
    otabase_blacklist_active.erase(
        std::remove(otabase_blacklist_active.begin(), otabase_blacklist_active.end(), msg_and_fields),
        otabase_blacklist_active.end());
    logger.log_info("OTABase: temp-blacklist reset for {}", msg_and_fields);
  }
}
