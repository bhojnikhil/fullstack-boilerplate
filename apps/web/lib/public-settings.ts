function templateValue(value: string | undefined, placeholder: string) {
  const text = value?.trim();
  return text && !text.startsWith("{{") ? text : placeholder;
}

export function appName(placeholder = "[App name]") {
  return templateValue(process.env.WEB_LEGAL_APP_NAME, placeholder);
}

export function legalDetails() {
  return {
    appName: appName(),
    domain: templateValue(process.env.WEB_LEGAL_DOMAIN, "[Site domain]"),
  };
}

export function supportEmail() {
  const email = process.env.WEB_SUPPORT_EMAIL?.trim();
  // Accept a single mailbox address without mailto URL delimiters.
  return email && /^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$/.test(email) ? email : undefined;
}

const warnedSettings = new Set<string>();

export function warnInvalidSetting(name: string, reason: string) {
  if (warnedSettings.has(name)) return;
  warnedSettings.add(name);
  console.warn(`[web] ${name} ${reason}`);
}

export function configuredValue<T>(
  name: string,
  parse: (value: string) => T | undefined,
) {
  const value = process.env[name]?.trim();
  if (!value) return undefined;
  const parsed = parse(value);
  if (parsed === undefined) warnInvalidSetting(name, "has an invalid value.");
  return parsed;
}

export function commaSeparated(value: string) {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}
