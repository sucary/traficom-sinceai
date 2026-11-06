SPACE_TABLES = (
    "notice", "grp", "freq", "assgn", "emiss", "s_beam", "geo",
    "non_geo", "orbit", "pub_ssn", "srs_ooak",
)

TERRESTRIAL_TABLES = (
    "circ", "pub_current_circ", "fxm_terra", "fxm_tx", "fxm_rx",
    "fxm_ant", "fxm_status", "fxm_pub_hist", "ref_adm", "ref_stn_cls",
)

SHEET = "Frequencies of interest"

SYNTHETIC_WORKBOOK = "Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx"

HEADERS = (
    "station_number", "licence_class", "longitude", "latitude", "ground_height_m",
    "mast_height_m", "mast_type", "channel_bandwidth", "tx_frequency", "rx_frequency",
    "antenna_height_agl_m", "antenna_height_asl_m", "antenna_gain_db", "emission_class",
    "transmission_bandwidth", "radiation_direction_deg", "polarisation", "reported_power",
    "power_reference_code", "power_unit", "line_loss_db", "directivity",
)
