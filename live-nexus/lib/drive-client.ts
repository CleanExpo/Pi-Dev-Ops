/** Drive REST helpers callable from Edge Runtime.
 * No googleapis npm dep at runtime — direct fetch keeps the edge bundle small. */

const DRIVE_UPLOAD_URL =
  "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";

interface ServiceAccountKey {
  client_email: string;
  private_key: string;
  token_uri?: string;
}

export interface DriveCreateResult {
  fileId: string;
  webViewLink: string;
}

/** Mint a short-lived access token from a service-account JWT.
 * Uses the WebCrypto API available in Edge Runtime. */
export async function mintServiceAccountToken(
  saKey: ServiceAccountKey
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = {
    iss: saKey.client_email,
    scope: "https://www.googleapis.com/auth/drive.file",
    aud: saKey.token_uri || GOOGLE_TOKEN_URL,
    iat: now,
    exp: now + 3600,
  };

  const enc = (o: object) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unsigned = `${enc(header)}.${enc(claim)}`;

  const pem = saKey.private_key
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const binDer = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "pkcs8",
    binDer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(unsigned)
  );
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const jwt = `${unsigned}.${sigB64}`;

  const tokenRes = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt,
    }),
  });
  if (!tokenRes.ok) {
    const text = await tokenRes.text();
    throw new Error(
      `Service-account token mint failed: ${tokenRes.status} ${text.slice(0, 200)}`
    );
  }
  const { access_token } = (await tokenRes.json()) as { access_token: string };
  return access_token;
}

export interface CreateDriveFileInput {
  accessToken: string;
  folderId: string;
  filename: string;
  content: string;
  mimeType: string;
}

export async function createDriveFile(
  input: CreateDriveFileInput
): Promise<DriveCreateResult> {
  const boundary = `boundary_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const metadata = JSON.stringify({
    name: input.filename,
    parents: [input.folderId],
    mimeType: input.mimeType,
  });

  const body =
    `--${boundary}\r\n` +
    `Content-Type: application/json; charset=UTF-8\r\n\r\n` +
    metadata +
    `\r\n` +
    `--${boundary}\r\n` +
    `Content-Type: ${input.mimeType}\r\n\r\n` +
    input.content +
    `\r\n` +
    `--${boundary}--`;

  const res = await fetch(`${DRIVE_UPLOAD_URL}&fields=id,webViewLink`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${input.accessToken}`,
      "Content-Type": `multipart/related; boundary=${boundary}`,
    },
    body,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Drive create failed: ${res.status} ${text.slice(0, 200)}`);
  }

  const data = (await res.json()) as { id: string; webViewLink?: string };
  return { fileId: data.id, webViewLink: data.webViewLink ?? "" };
}
