// Only the Vercel build runs this check. Local Vite keeps using API_PROXY_TARGET.
const value = process.env.BACKEND_URL;
let valid = false;
try {
  const url = new URL(value);
  valid = url.protocol === 'https:' && url.origin === value
    && !url.username && !url.password
    && url.hostname !== 'localhost' && !url.hostname.endsWith('.localhost')
    && !url.hostname.startsWith('[') && !/^\d+\.\d+\.\d+\.\d+$/.test(url.hostname);
} catch {
  // Report the setting name, never its possibly sensitive value.
}
if (!valid) {
  console.error('Set BACKEND_URL to the authenticated public HTTPS origin, without a trailing slash, path, query or credentials. Use a public DNS hostname for this configuration.');
  process.exit(1);
}
console.log('BACKEND_URL format checked. Test gateway authentication and connectivity before deployment.');
