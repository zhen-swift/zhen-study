"""The collection harness.

Python, and deliberately independent of the thing it measures: no module in this
package may import from netsanity, and `run_block.py --self-check` asserts that by
reading this package's own source rather than by trusting the comment.  A harness that
shares code with the system under test can share a bug with it, and a reviewer is
entitled to assume the worst.

The harness collects; it never computes a statistic.  Everything it knows leaves through
one append-only NDJSON file, and `Study/analysis/` reads that file and never touches the
network.
"""

SCHEMA_VERSION = 1
