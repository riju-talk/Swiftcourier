import re


def validate_hub(
    name: str,
    address_line1: str,
    address_line2: str,
    city: str,
    state: str,
    country: str,
    pin_code: str,
    contact_person: str,
    phone: str,
    alt_phone: str,
    email: str,
    gstin: str,
) -> str:
    # Helper regex patterns
    phone_regex = r"^\d{10}$"
    pin_regex = r"^\d{6}$"

    # Name
    if len(name.strip()) < 5:
        return "Name must be at least 5 characters."

    # Address lines
    if len(address_line1.strip()) < 5:
        return "Address line 1 must be at least 5 characters."

    # City, State, Country
    if len(city.strip()) < 2:
        return "City must be alphabetic and at least 2 characters."
    if len(state.strip()) < 2:
        return "State must be alphabetic and at least 2 characters."
    if len(country.strip()) < 2:
        return "Country must be alphabetic and at least 2 characters."

    # Pin code
    if not re.match(pin_regex, pin_code.strip()):
        return "PIN code must be exactly 6 digits."

    # Contact person
    if len(contact_person.strip()) < 3 or not all(
        x.isalpha() or x.isspace() for x in contact_person
    ):
        return "Contact person name must be alphabetic and at least 3 characters."

    # Phone numbers
    if not re.match(phone_regex, phone):
        return "Phone number must be exactly 10 digits."
    if alt_phone and not re.match(phone_regex, alt_phone):
        return "Alternate phone number must be exactly 10 digits if provided."

    return None
