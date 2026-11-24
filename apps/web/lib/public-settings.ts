function templateValue(value: string | undefined, placeholder: string) {
  const text = value?.trim();
  return text && !text.startsWith("{{") ? text : placeholder;
}

export function legalDetails() {
  return {
    appName: templateValue(process.env.WEB_LEGAL_APP_NAME, "[App name]"),
    domain: templateValue(process.env.WEB_LEGAL_DOMAIN, "[Site domain]"),
  };
}

export function supportEmail() {
  const email = process.env.WEB_SUPPORT_EMAIL?.trim();
  // Accept a single mailbox address without mailto URL delimiters.
  return email && /^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$/.test(email) ? email : undefined;
}
