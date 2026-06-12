# LSE Prompt — Meross Bulb Diagnostic Investigation
# Entity: light.smart_rgb_bulb_2104097726182590848948e1e96af34b
# Paste into OWUI LSE chat with lse_vaultwarden_tools enabled

Step 1: vault_unlock() -> get_vault_secret("ha-token") -> store as ha_token

Step 2: Get current entity state and attributes
execute_command("""curl -s \
  -H 'Authorization: Bearer '"$ha_token"'' \
  http://homeassistant.home.arpa:8123/api/states/light.smart_rgb_bulb_2104097726182590848948e1e96af34b \
  | jq '{state, last_changed, last_updated, context, attributes: {friendly_name, supported_features, effect_list, brightness, color_mode, supported_color_modes}}'""")

Step 3: Pull logbook for the last 7 days — separate spontaneous from triggered events
execute_command("""curl -s \
  -H 'Authorization: Bearer '"$ha_token"'' \
  'http://homeassistant.home.arpa:8123/api/logbook/2026-06-03T00:00:00+00:00?entity_id=light.smart_rgb_bulb_2104097726182590848948e1e96af34b' \
  | jq '
    {
      total: length,
      spontaneous_turnons: [.[] | select(.state=="on" and .context_user_id==null and .context_parent_id==null) | {when: .when, state: .state, context_id: .context_id}],
      automation_triggered: [.[] | select(.context_parent_id!=null) | {when: .when, state: .state, source: .context_user_id, parent: .context_parent_id}],
      user_triggered: [.[] | select(.context_user_id!=null) | {when: .when, state: .state, user: .context_user_id}]
    }
  '""")

Step 4: List all automations — find any that reference this entity or the Meross integration
execute_command("""curl -s \
  -H 'Authorization: Bearer '"$ha_token"'' \
  http://homeassistant.home.arpa:8123/api/states \
  | jq '[.[] | select(.entity_id | startswith("automation.")) | {entity_id, state, last_triggered: .attributes.last_triggered, friendly_name: .attributes.friendly_name}] | sort_by(.last_triggered) | reverse'""")

Step 5: List all scripts — find any that reference light or meross
execute_command("""curl -s \
  -H 'Authorization: Bearer '"$ha_token"'' \
  http://homeassistant.home.arpa:8123/api/states \
  | jq '[.[] | select(.entity_id | startswith("script.")) | {entity_id, state, last_triggered: .attributes.last_triggered, friendly_name: .attributes.friendly_name}]'""")

Step 6: Check HA error log for meross/mqtt/bulb errors
execute_command("""curl -s \
  -H 'Authorization: Bearer '"$ha_token"'' \
  http://homeassistant.home.arpa:8123/api/error_log \
  | grep -i -E '(meross|smart_rgb|2104097726|mqtt|msl120|48:e1:e9)' | tail -50""")

Step 7: Get the meross_lan config entry details to confirm MQTT mode is active
execute_command("""curl -s \
  -H 'Authorization: Bearer '"$ha_token"'' \
  http://homeassistant.home.arpa:8123/api/config/config_entries \
  | jq '[.[] | select(.domain=="meross_lan") | {entry_id, title, state, domain, options}]'""")

Step 8: Report findings — summarise:
  - How many spontaneous turn-on events in the last 7 days and when
  - Whether any automation has last_triggered correlating with those timestamps
  - Whether any automation name references meross, bulb, light, scene, or schedule
  - MQTT protocol confirmed active (from step 7)
  - Any relevant errors from the error log
  - Recommendation: suppress-automation needed Y/N, or if an automation is the actual cause

DO NOT: store ha_token in any file or env var -- retrieve from vault each session
DO NOT: call GET /api/history without a date filter -- response can be enormous
DO NOT: write to /config/ without first confirming SSH key access to homeassistant.home.arpa
DO NOT: reload_config_entry without confirming entry_id from GET /api/config/config_entries
