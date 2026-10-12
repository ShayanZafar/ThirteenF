# Core flows

This file lists what a person relies on ThirteenF for and names, for each flow, the tests at each level the [definition of done](../CLAUDE.md#definition-of-done) asks for: unit (one module, no network), integration (real routes, DuckDB or the ingest pipeline together, outside services played by stand-ins) and UI (a real browser driving the running app), with `—` for a gap. `scripts/verify.sh` checks it with `scripts/check_core_flows.py`, failing when a flow lacks a level, a named test no longer exists, or the gaps differ from the count below, which only ever goes down.

Gaps allowed: 16

| Flow | Unit | Integration | UI |
|---|---|---|---|
| Refresh the data from the SEC | `tests/test_ingest.py` › test_links_come_from_the_page_in_either_folder<br>`tests/test_sec_retry.py` › test_a_busy_server_is_asked_again_within_seconds | `tests/test_ingest.py` › test_loading_the_same_zip_twice_does_not_duplicate_rows<br>`tests/test_seams.py` › test_the_made_up_data_builds_every_period | — |
| See where funds are moving across the market (Biggest changes) | — | — | — |
| Look up one stock and see who added and who left | `tests/test_story.py` › test_streaks<br>`tests/test_story.py` › test_one_period_change_after_a_streak | `tests/test_seams.py` › test_search_keeps_an_ampersand_in_the_query<br>`tests/test_ticker_fallbacks.py` › test_a_database_built_before_ticker_sources_still_shows_its_stocks | — |
| Keep a watchlist of stocks on the overview | — | — | — |
| Find stocks to accumulate | — | `tests/test_accumulate.py` › test_the_list_holds_stocks_funds_keep_moving_into<br>`tests/test_accumulate.py` › test_banks_and_insurers_are_left_out | — |
| See a manager's portfolio and download it as CSV | — | — | — |
| Get a ticker for every CUSIP, even when OpenFIGI is down | `tests/test_openfigi.py` › test_check_digits<br>`tests/test_ticker_fallbacks.py` › test_names_written_differently_normalise_alike | `tests/test_seams.py` › test_a_connection_that_stays_down_never_stops_the_run<br>`tests/test_ticker_fallbacks.py` › test_the_fails_to_deliver_data_answers_first_then_the_issuer_name | — |
| See how fresh each number is and where it came from | `tests/test_periods.py` › test_deadline_is_45_days_after_quarter_end | `tests/test_ticker_fallbacks.py` › test_when_openfigi_is_down_the_chain_answers_and_the_page_says_where_from | — |
| Be told when a data source stops answering | `tests/test_health.py` › test_a_source_is_unreliable_after_five_attempts_with_under_half_answered | `tests/test_ticker_fallbacks.py` › test_tickers_count_as_unreliable_once_openfigi_and_its_fallback_both_are | — |
