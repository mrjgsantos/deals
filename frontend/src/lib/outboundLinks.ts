const AMAZON_ES_HOSTS = new Set(["amazon.es", "www.amazon.es"]);
const AMAZON_ES_AFFILIATE_TAG = import.meta.env.VITE_AMAZON_ES_AFFILIATE_TAG?.trim() ?? "";

export function toOutboundAmazonUrl(url: string | null): string | null {
  if (!url) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }

  if (!AMAZON_ES_HOSTS.has(parsed.hostname.toLowerCase())) {
    return url;
  }

  if (!AMAZON_ES_AFFILIATE_TAG) {
    return url;
  }

  parsed.searchParams.set("tag", AMAZON_ES_AFFILIATE_TAG);
  return parsed.toString();
}
