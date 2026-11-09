#!/usr/bin/env bash
# Exercise the actual entrypoint without Python, Django, media tools or services.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -f "$fixture/python" "$fixture/calls"; rmdir "$fixture"' EXIT
cat > "$fixture/python" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
[[ "${DJANGO_SETTINGS_MODULE:-}" == config.settings.render ]]
printf '%s\n' "$*" >> "$STARTUP_TEST_LOG"
case "$*" in
  '-m config.runtime_requirements') exit "$MEDIA_PROBE_FAILURE" ;;
  '-m gunicorn config.wsgi:application --config gunicorn.native.py') exit 0 ;;
  *) echo 'Unexpected Python invocation.' >&2; exit 99 ;;
esac
STUB
chmod +x "$fixture/python"

for failure in 124 127; do
  # Simulate the runtime gate timing out or finding no multimedia executable.
  for mode in web default; do
    : > "$fixture/calls"
    args=()
    if [[ "$mode" == web ]]; then args=(web); fi
    PATH="$fixture:$PATH" RENDER=true STARTUP_TEST_LOG="$fixture/calls" \
      MEDIA_PROBE_FAILURE="$failure" bash "$root/backend/native-start.sh" "${args[@]}"
    [[ "$(< "$fixture/calls")" == '-m gunicorn config.wsgi:application --config gunicorn.native.py' ]]
  done

  # Workers still run and enforce the dependency gate before launching jobs.
  : > "$fixture/calls"
  status=0
  PATH="$fixture:$PATH" RENDER=true STARTUP_TEST_LOG="$fixture/calls" \
    MEDIA_PROBE_FAILURE="$failure" bash "$root/backend/native-start.sh" worker || status=$?
  [[ "$status" == "$failure" ]]
  [[ "$(< "$fixture/calls")" == '-m config.runtime_requirements' ]]
done
echo 'PASS: default/explicit Render web startup skips failed media probes; workers retain validation.'
