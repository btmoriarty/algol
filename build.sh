#!/usr/bin/env bash
# Package the algol skill as an installable .skill bundle.
# Usage: ./build.sh
# On Windows, use: Compress-Archive -Path skills/algol -DestinationPath algol.zip
#   then rename algol.zip to algol.skill
set -euo pipefail
cd "$(dirname "$0")"
rm -f algol.skill
(cd skills && zip -r ../algol.skill algol -x '*.DS_Store')
echo "Built algol.skill"
