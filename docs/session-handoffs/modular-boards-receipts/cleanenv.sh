#!/usr/bin/env bash
# Strip container-ambient credentials/config that the repo's tests treat as hostile ambient state.
exec env -u HTTPS_PROXY -u https_proxy -u HTTP_PROXY -u http_proxy -u ANTHROPIC_BASE_URL -u GH_TOKEN -u GITHUB_TOKEN \
  -u GIT_CONFIG_COUNT -u GIT_CONFIG_KEY_0 -u GIT_CONFIG_VALUE_0 -u GIT_CONFIG_KEY_1 -u GIT_CONFIG_VALUE_1 -u GIT_CONFIG_KEY_2 -u GIT_CONFIG_VALUE_2 setpriv --inh-caps=-dac_override,-dac_read_search --bounding-set=-dac_override,-dac_read_search "$@"
