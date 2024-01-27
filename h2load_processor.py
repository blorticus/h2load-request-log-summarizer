#!/usr/bin/env python3

'''A processor for the output log from h2load.

SYNOPSIS

h2load_processor.py </path/to/log/file> [-o </path/to/output/file>]

DESCRIPTION

Read the log file from h2load and produce summary statistics.  The log file must be
whitespace delimited records with rows separated by newlines.  Each line must have
three columns, each an integer.  The columns are:

  requestTimestamp     responseCode    timeToLastByte

The first and third are in microseconds.  The second is the HTTP/2 response code,
or -1 if the stream failed.

The processor generates a CSV summary file from the raw data.  By default, it is
printed to stdout, but may be written to a file using the -o flag.  The summary is
as follows (line breaks inserted here for clarity):

  type,key,totalRequests,successfulRequests,failurePercentage,
  ttlbMean,ttlbMedian,ttlbStdev,ttlb5thPercentile,ttlb95thPercentile,
  aggregateTPS,movingTPSMean,movingTPSMedian,movingTPSStdev

The "type" is "global" or "responseCode".  There is a single row for "global"
and contains the stats across all requests.  For this row, "key" is the empty string.
For "responseCode", there is one row for each unique response code.  In this case,
the "key" for each row is the unique response code.  The statistics in each row
corresponds to the statistics for requests that generated the corresponding response
code.

For each row, "totalRequests" is the number of requests matching the type and key.
"successfulRequests" is a count of the requests that resulted in a 2xx response code.
"failurePercentage" is the percentage of the totalRequests that resulted in any other
response code.  "ttlbMean" is the mean for all timeToLastByte entries that match
the type and key (in microseconds).  "ttlbMedian" and "ttlbStdev" are the median
and populated standard deviation for the timeToLastByte for all entries that match the
type and key.  Since the precision of the source is 1 microsecond, all of the results
will contain no more than one more degree of precision.  That is, values will have
no more than one decimal place.  Rounding follows normal arithmetic rounding rules.
The "ttlb5thPercentile" is the value at the 5th percentile in the series.  To retrieve
this, the set must have at least 20 rows.  If it has fewer, then this
field will be empty.  The latency95thHigh is the same thing (with the same restriction)
but at the 95th percentile mark.  The 5th percentile is computed by (n - n * 0.05) where
'n' is the row count.  For example, when n = 100, with the latency values in ascending
order, the 5th value is the 5thPercentile, while the 95th value is the 95thPercentile.
'''

import argparse
import re
import sys
from statistics import mean, median, pstdev, quantiles

h2load_row_re = re.compile(r'^(\d+)\s+(\-?\d+)\s+(\d+)$')


def main():
    '''Entrypoint.'''
    cli_argument = process_command_line_arguments()

    count_of_transactions_each_second = {}
    number_of_requests_sent = 0
    ttlb_list_for_each_response_code: dict[int, list[int]] = {}
    ttlb_list_for_all_response_codes: list[int] = []

    timestamp_of_first_entry: int = -1
    timestamp_of_last_entry: int = -1

    line_number = 0
    with open(cli_argument.h2load_filename, 'r', encoding='latin-1') as h2load_file:
        for data_row in h2load_file:
            line_number += 1

            match = h2load_row_re.match(data_row)
            if match is None:
                die(f"Invalid row on line {line_number}")
                return

            request_start_time_ms, response_code, ttlb_ms = int(match.group(1)), int(match.group(2)), int(match.group(3))
            timestamp_sec_that_response_was_received = round((request_start_time_ms + ttlb_ms) / 1e6)

            if line_number == 1:
                timestamp_of_first_entry = timestamp_sec_that_response_was_received

            timestamp_of_last_entry = timestamp_sec_that_response_was_received

            if timestamp_sec_that_response_was_received not in count_of_transactions_each_second:
                count_of_transactions_each_second[timestamp_sec_that_response_was_received] = 1
            else:
                count_of_transactions_each_second[timestamp_sec_that_response_was_received] += 1

            number_of_requests_sent += 1

            if response_code not in ttlb_list_for_each_response_code:
                ttlb_list_for_each_response_code[response_code] = [ttlb_ms]
            else:
                ttlb_list_for_each_response_code[response_code].append(ttlb_ms)

            ttlb_list_for_all_response_codes.append(ttlb_ms)

    output_file_handle = sys.stdout
    if cli_argument.output is not None and cli_argument.output != "":
        output_file_handle = open(cli_argument.output, 'w', encoding='utf-8')

    moving_tps_list = list(count_of_transactions_each_second.values())

    aggregate_ttlb_mean = round(mean(ttlb_list_for_all_response_codes), 1)
    aggregate_ttlb_median = round(median(ttlb_list_for_all_response_codes), 1)
    aggregate_ttlb_stdev = round(pstdev(ttlb_list_for_all_response_codes), 1)
    quantiles_of_20 = quantiles(ttlb_list_for_all_response_codes, n=20)
    ttlb_5th_percentile = round(quantiles_of_20[0], 1)
    ttlb_95th_percentile = round(quantiles_of_20[18], 1)

    number_of_responses_that_are_2xx = 0
    number_of_non_2xx_responses = 0

    for response_code, ttlb_list_for_that_response_code in ttlb_list_for_each_response_code.items():
        count_of_responses_with_that_response_code = len(ttlb_list_for_that_response_code)
        if 200 <= response_code < 300:
            number_of_responses_that_are_2xx += count_of_responses_with_that_response_code
        else:
            number_of_non_2xx_responses += count_of_responses_with_that_response_code

    aggregate_tps = 0
    if timestamp_of_first_entry > -1:
        if timestamp_of_first_entry == timestamp_of_last_entry:
            aggregate_tps = 1
        else:
            aggregate_tps = round(number_of_requests_sent / (timestamp_of_last_entry - timestamp_of_first_entry))

    moving_tps_mean, moving_tps_median, moving_tps_stdev = round(mean(moving_tps_list), 1), round(median(moving_tps_list), 1), round(pstdev(moving_tps_list), 1)

    print(
        "type,key,totalRequests,successfulRequests,failedRequests," +
        "ttlbMean,ttlbMedian,ttlbStdev,ttlb5thPercentile,ttlb95thPercentile," +
        "aggregateTPS,movingTPSMean,movingTPSMedian,movingTPSStdev",
        file=output_file_handle
    )

    print(generate_summary_line("Aggregate", "", number_of_requests_sent, number_of_responses_that_are_2xx,
                                aggregate_ttlb_mean, aggregate_ttlb_median, aggregate_ttlb_stdev, ttlb_5th_percentile, ttlb_95th_percentile,
                                aggregate_tps, moving_tps_mean, moving_tps_median, moving_tps_stdev),
          file=output_file_handle)

def generate_summary_line(key_type: str, key: str, total_requests: int, successful_requests: int,
                        ttlb_mean: float, ttlb_median: float, ttlb_stdev: float, ttlb_5th: float, ttlb_95th: float,
                        aggregate_tps: float, moving_tps_mean: float, moving_tps_median: float, moving_tps_stdev: float) -> str:
    '''Generate a line (without trailing newline) of comma-separated records matching the columns in the header line.'''
    return ",".join([
        key_type, key, str(total_requests), str(successful_requests), str(total_requests - successful_requests),
        str(ttlb_mean), str(ttlb_median), str(ttlb_stdev), str(ttlb_5th), str(ttlb_95th),
        str(aggregate_tps), str(moving_tps_mean), str(moving_tps_median), str(moving_tps_stdev)
    ])

def process_command_line_arguments() -> argparse.Namespace:
    '''Process command-line argument, returning the parse_args result from an argparse object.'''
    parser = argparse.ArgumentParser(description="Produce summary statistics from an h2load log file.")
    parser.add_argument("h2load_filename", help="path to the h2load log file which should be processed", type=str)
    parser.add_argument("-o", "--output", help="path to the output CSV filename", type=str)

    return parser.parse_args()

def die(msg: str):
    '''Print msg to stderr and exit with non-zero value.'''
    print(msg, file=sys.stderr)
    sys.exit(1)

if __name__ == '__main__':
    main()
