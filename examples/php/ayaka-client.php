<?php
// AYAKA API — contoh integrasi PHP 7.4+ (ext-curl, ext-json). Powered by AYAKA Sync.
// Jalankan: AYAKA_BASE_URL=https://domain-anda.vercel.app AYAKA_API_KEY=ayaka_live_xxx php ayaka-client.php user@example.com

final class AyakaClient
{
    private string $baseUrl;
    private string $apiKey;

    public function __construct(string $baseUrl, string $apiKey)
    {
        $this->baseUrl = rtrim($baseUrl, '/');
        $this->apiKey = $apiKey;
    }

    public function request(string $method, string $path, ?array $body = null): array
    {
        $ch = curl_init($this->baseUrl . $path);
        $headers = ['X-API-Key: ' . $this->apiKey, 'Accept: application/json'];
        $opts = [CURLOPT_CUSTOMREQUEST => $method, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 20];
        if ($body !== null) {
            $headers[] = 'Content-Type: application/json';
            $opts[CURLOPT_POSTFIELDS] = json_encode($body);
        }
        $opts[CURLOPT_HTTPHEADER] = $headers;
        curl_setopt_array($ch, $opts);
        $raw = curl_exec($ch);
        if ($raw === false) {
            throw new RuntimeException('Koneksi gagal: ' . curl_error($ch));
        }
        $status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        curl_close($ch);
        $json = json_decode($raw, true) ?: ['success' => false, 'message' => 'Respons bukan JSON'];
        if ($status >= 400 || empty($json['success'])) {
            $code = $json['error']['code'] ?? 'HTTP_' . $status;
            throw new RuntimeException("[$status $code] " . ($json['message'] ?? 'Error'));
        }
        return $json['data'] ?? [];
    }

    public function profile(): array { return $this->request('GET', '/api/user/profile'); }
    public function keys(): array { return $this->request('GET', '/api/keys'); }
    public function revokeKey(string $id): array { return $this->request('DELETE', '/api/keys/' . rawurlencode($id)); }
    public function sendMagicLink(string $email, string $plan = 'premium'): array { return $this->request('POST', '/api/am/send', ['email' => $email, 'plan' => $plan]); }
    public function status(string $email): array { return $this->request('GET', '/api/am/status?email=' . rawurlencode($email)); }
    public function renew(string $email, int $days): array { return $this->request('POST', '/api/am/renew', ['email' => $email, 'duration_days' => $days]); }
    public function revokePremium(string $email, ?string $reason = null): array { return $this->request('POST', '/api/am/revoke', ['email' => $email, 'reason' => $reason]); }
}

if (PHP_SAPI === 'cli' && realpath($argv[0]) === __FILE__) {
    $key = getenv('AYAKA_API_KEY');
    if (!$key) { fwrite(STDERR, "Set AYAKA_API_KEY terlebih dahulu\n"); exit(1); }
    $client = new AyakaClient(getenv('AYAKA_BASE_URL') ?: 'http://localhost:8000', $key);
    try {
        print_r($client->profile());
        if (!empty($argv[1])) print_r($client->status($argv[1]));
    } catch (RuntimeException $e) {
        fwrite(STDERR, $e->getMessage() . "\n"); exit(1);
    }
}
