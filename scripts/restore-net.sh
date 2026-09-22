#!/usr/bin/env bash
# Desktop-action target. Exec= lines may not contain shell metacharacters, so
# the redirect lives here rather than in the .desktop file.
echo give-back > "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/control/request"
