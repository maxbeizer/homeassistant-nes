"""Constants for the Nashville Electric Service (NES) integration."""

import logging

DOMAIN = "nes"
LOGGER = logging.getLogger(__package__)

ATTRIBUTION = "Data provided by Nashville Electric Service"

# Azure AD B2C configuration
B2C_TENANT = "pdnesb2c"
B2C_POLICY = "b2c_1a_nes_signuporsignin"
B2C_CLIENT_ID = "1414bb49-913f-48f8-851c-f14718104471"
B2C_REDIRECT_URI = "https://myaccount.nespower.com/eportal"
B2C_SCOPE = "openid profile offline_access"

B2C_BASE_URL = (
    f"https://{B2C_TENANT}.b2clogin.com/"
    f"{B2C_TENANT}.onmicrosoft.com/{B2C_POLICY}"
)
B2C_AUTHORIZE_URL = f"{B2C_BASE_URL}/oauth2/v2.0/authorize"
B2C_TOKEN_URL = f"{B2C_BASE_URL}/oauth2/v2.0/token"
B2C_SELF_ASSERTED_URL = f"{B2C_BASE_URL}/SelfAsserted"
B2C_CONFIRMED_URL = f"{B2C_BASE_URL}/api/CombinedSigninAndSignup/confirmed"

# NES API
API_BASE_URL = "https://myaccount.nespower.com"
API_ENDPOINT_CUSTOMER = "/rest/account/customer/"

# Polling interval (seconds)
UPDATE_INTERVAL_HOURS = 6
