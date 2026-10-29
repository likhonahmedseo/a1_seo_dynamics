#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python3"

echo ""
echo "========================================================================"
echo "  A1 Mail Dynamics - Customer License Generator"
echo "========================================================================"
echo ""

if [[ ! -f "private/vendor-license-private.pem" ]]; then
  echo "ERROR: Private key not found!"
  echo ""
  echo "Run this first to generate vendor keys:"
  echo "  $PYTHON tools/generate_license_keys.py --private-key private/vendor-license-private.pem"
  echo ""
  exit 1
fi

if [[ ! -f "$PYTHON" ]]; then
  echo "[ERROR] Virtual environment not found at $PYTHON"
  echo "Create it with: python3 -m venv .venv && .venv/bin/pip install cryptography"
  exit 1
fi

echo "Enter customer details:"
echo ""
read -r -p "Customer/Company Name: " CUSTOMER_NAME
if [[ -z "$CUSTOMER_NAME" ]]; then
  echo "ERROR: Customer name is required."
  exit 1
fi

read -r -p "Customer Email: " CUSTOMER_EMAIL
if [[ -z "$CUSTOMER_EMAIL" ]]; then
  echo "ERROR: Customer email is required."
  exit 1
fi

echo ""
echo "------------------------------------------------------------------------"
echo "License Plan"
echo "  Option 1: 7-Day Trial                (any machine, expires after 7 days)"
echo "  Option 2: 30-Day Subscription        (machine-bound, renewable)"
echo "  Option 3: 1-Year Subscription        (machine-bound, renewable)"
echo "  Option 4: Perpetual Lifetime License (machine-bound)"
echo "------------------------------------------------------------------------"
echo ""
read -r -p "Choose option (1, 2, 3, or 4): " LICENSE_OPTION

require_machine_id() {
  echo ""
  echo "The customer will see their Machine ID in the app on the License Activation screen."
  read -r -p "Enter customer's Machine ID: " MACHINE_ID
  if [[ -z "$MACHINE_ID" ]]; then
    echo "ERROR: Machine ID is required for this license."
    exit 1
  fi
  MACHINE_ID="${MACHINE_ID:0:32}"
}

case "$LICENSE_OPTION" in
  1)
    echo ""
    echo "Creating 7-day trial license (any machine)"
    MACHINE_ID="*"
    LICENSE_TYPE="7-Day Trial"
    DURATION_DAYS=7
    DESC="7-Day Trial (any machine)"
    RENEWAL_NOTE="Issue a fresh trial key only if you want to extend a demo."
    ;;
  2)
    require_machine_id
    echo ""
    echo "Creating 30-day subscription license for machine $MACHINE_ID"
    LICENSE_TYPE="30-Day Subscription"
    DURATION_DAYS=30
    DESC="30-Day Subscription (bound to $MACHINE_ID)"
    RENEWAL_NOTE="To renew, generate a new 30-day key for the same Machine ID and send it to the customer."
    ;;
  3)
    require_machine_id
    echo ""
    echo "Creating 1-year subscription license for machine $MACHINE_ID"
    LICENSE_TYPE="1-Year Subscription"
    DURATION_DAYS=365
    DESC="1-Year Subscription (bound to $MACHINE_ID)"
    RENEWAL_NOTE="To renew, generate a new 1-year key for the same Machine ID and send it to the customer."
    ;;
  4)
    require_machine_id
    echo ""
    echo "Creating perpetual lifetime license for machine $MACHINE_ID"
    LICENSE_TYPE="Perpetual Lifetime"
    DURATION_DAYS=0
    DESC="Perpetual Lifetime (bound to $MACHINE_ID)"
    RENEWAL_NOTE="No expiry. Reissue only if the customer changes machine."
    ;;
  *)
    echo "ERROR: Invalid option. Please choose 1, 2, 3, or 4."
    exit 1
    ;;
esac

echo ""
echo "------------------------------------------------------------------------"
echo "Generating license..."
echo "------------------------------------------------------------------------"

DURATION_ARGS=()
if [[ "$DURATION_DAYS" -gt 0 ]]; then
  DURATION_ARGS=(--duration-days "$DURATION_DAYS")
fi

LICENSE_TOKEN=$("$PYTHON" tools/generate_license_token.py \
  --private-key private/vendor-license-private.pem \
  --customer-name "$CUSTOMER_NAME" \
  --customer-email "$CUSTOMER_EMAIL" \
  --machine-id "$MACHINE_ID" \
  --license-type "$LICENSE_TYPE" \
  "${DURATION_ARGS[@]+"${DURATION_ARGS[@]}"}")

mkdir -p private/licenses
FILENAME="${CUSTOMER_NAME// /_}_${LICENSE_TYPE// /_}"
FILENAME="${FILENAME//-/_}"
OUTPUT_FILE="private/licenses/${FILENAME}_License.txt"

{
  echo "Customer Name: $CUSTOMER_NAME"
  echo "Customer Email: $CUSTOMER_EMAIL"
  echo "License Type: $DESC"
  echo "Machine ID: $MACHINE_ID"
  echo "Generated: $(date)"
  echo "Renewal: $RENEWAL_NOTE"
  echo ""
  echo "ACTIVATION KEY:"
  echo "$LICENSE_TOKEN"
} > "$OUTPUT_FILE"

echo ""
echo "========================================================================"
echo "  LICENSE GENERATED SUCCESSFULLY"
echo "========================================================================"
echo ""
echo "Customer: $CUSTOMER_NAME"
echo "Email:    $CUSTOMER_EMAIL"
echo "Type:     $DESC"
echo "Renewal:  $RENEWAL_NOTE"
echo ""
echo "------------------------------------------------------------------------"
echo "ACTIVATION KEY"
echo "------------------------------------------------------------------------"
echo "$LICENSE_TOKEN"
echo "------------------------------------------------------------------------"
echo ""
echo "Saved to: $OUTPUT_FILE"
echo ""
echo "Send to Customer:"
echo "  1. Customer opens the app and reaches the License Activation screen"
echo "  2. Customer pastes the activation key above"
echo "  3. The app activates or renews immediately on that machine"
echo ""

# Copy to clipboard (macOS)
if command -v pbcopy &>/dev/null; then
  echo "$LICENSE_TOKEN" | pbcopy
  echo "Activation key copied to clipboard!"
fi
echo ""
