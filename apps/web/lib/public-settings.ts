function templateValue(value: string | undefined, placeholder: string) {
  const text = value?.trim();
  return text && !text.startsWith("{{") ? text : placeholder;
}

export function appName(placeholder = "Full-stack starter") {
  return templateValue(process.env.WEB_LEGAL_APP_NAME, placeholder);
}

export function legalDetails() {
  return {
    appName: appName("[App name]"),
    domain: templateValue(process.env.WEB_LEGAL_DOMAIN, "[Site domain]"),
  };
}

export function supportEmail() {
  const email = process.env.WEB_SUPPORT_EMAIL?.trim();
  // Accept a single mailbox address without mailto URL delimiters.
  if (email && /^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$/.test(email)) return email;

  warnInvalidSetting(
    "WEB_SUPPORT_EMAIL",
    "is missing or invalid for account deletion requests.",
  );
  return undefined;
}

// Next can bundle startup instrumentation and routes separately in the same process.
const warningKey = Symbol.for("boilerplate.web.settings-warnings");
const warningState = globalThis as typeof globalThis & { [warningKey]?: Set<string> };

export function warnInvalidSetting(name: string, reason: string) {
  const warnedSettings = (warningState[warningKey] ??= new Set());
  if (warnedSettings.has(name)) return;
  warnedSettings.add(name);
  console.warn(`[web] ${name} ${reason}`);
}
