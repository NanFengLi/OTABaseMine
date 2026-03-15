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

#pragma once

#include "srsran/pdcp/pdcp_t_reordering.h"
#include "srsran/rrc/rrc_types.h"
#include <string>

namespace srsran {
namespace srs_cu_cp {

/// PDCP configuration for a SRB.
struct srb_pdcp_config {
  /// Value in ms of t-Reordering specified in TS 38.323.
  pdcp_t_reordering t_reordering = pdcp_t_reordering::infinity;
};

/// RRC UE configuration.
struct rrc_ue_cfg_t {
  /// PDCP configuration for SRB1.
  srb_pdcp_config              srb1_pdcp_cfg;
  std::vector<rrc_meas_timing> meas_timings;
  bool                         force_reestablishment_fallback = false;
  /// \brief Guard time used for RRC message exchange with UE.
  std::chrono::milliseconds rrc_procedure_guard_time_ms{500};
  /// Enable OTABase-style 5G RRC mutation message injection.
  bool otabase_enable_5g_rrc_fuzzing = false;
  /// Path to OTABase index file (for example: testFileIndex).
  std::string otabase_test_index_file = "testFileIndex";
  /// Oracle liveness check period (send UECapabilityEnquiry every N test messages).
  unsigned otabase_check_period = 10;
  /// Replay mode: disables blacklisting, reduces check_period to 2.
  bool otabase_replay_mode = false;
  /// Output directory for crash candidates (same as 4G -o). If empty, uses "otabase_crashes".
  std::string otabase_output_directory;
  /// Enable temporary blacklist (same as 4G temp_blacklist). When true, same msg+field timeout 3 times → temp skip; 30 lines skipped → remove.
  bool otabase_temp_blacklist = true;
};

} // namespace srs_cu_cp
} // namespace srsran
