

Getting the latest ev-data

LATEST_TAG=$(curl -s https://api.github.com/repos/open-ev-data/open-ev-data-dataset/releases/latest | grep '"tag_name"' | cut -d '"' -f 4)

echo "$LATEST_TAG"

curl -fL -o open-ev-data.json \
  "https://github.com/open-ev-data/open-ev-data-dataset/releases/download/$LATEST_TAG/open-ev-data-$LATEST_TAG.json"

