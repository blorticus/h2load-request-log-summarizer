# h2load-log

Process log output from h2load.

## Synopsis

```bash
h2load_processor.py </path/to/log/file> [-o </path/to/output/file>]
```

## Description

Read the log file from h2load and produce summary statistics.  The log file must be
whitespace delimited records with rows separated by newlines.  Each line must have
three columns, each an integer.  The columns are:

```text
  requestTimestamp     responseCode    timeToLastByte
```

The first and third are in microseconds.  The second is the HTTP/2 response code,
or -1 if the stream failed.

The processor generates a CSV summary file from the raw data.  By default, it is
printed to stdout, but may be written to a file using the -o flag.  The summary is
as follows (line breaks inserted here for clarity):

```text
  type,key,totalRequests,successfulRequests,failurePercentage,
  ttlbMean,ttlbMedian,ttlbStdev,ttlb5thPercentile,ttlb95thPercentile,
  aggregateTPS,movingTPSMean,movingTPSMedian,movingTPSStdev
```

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
