import FingerprintJS from '@fingerprintjs/fingerprintjs';

// Probabilistic device id (FingerprintJS open-source visitorId). Sent with signup so the
// backend can soft-flag many accounts from one device. Spoofable by design — it's a
// cost-raiser, not a wall. Cached for the page session; failures resolve to '' (the
// backend treats a missing device id as simply "no signal").
let cached: string | null = null;
let inflight: Promise<string> | null = null;

export async function getDeviceId(): Promise<string> {
  if (cached !== null) return cached;
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const fp = await FingerprintJS.load();
      const { visitorId } = await fp.get();
      cached = visitorId;
      return visitorId;
    } catch {
      cached = '';
      return '';
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}
