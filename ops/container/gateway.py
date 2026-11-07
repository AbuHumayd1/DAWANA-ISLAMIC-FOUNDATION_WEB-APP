"""Pure gateway rendering. No provider assumptions, network or secret output."""
from ipaddress import ip_network
import re


def configuration(env):
    host = env.get('PUBLIC_HOST', '')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host) or '.' not in host:
        raise ValueError('PUBLIC_HOST must be one exact approved DNS hostname.')
    port = env.get('PORT', '8080')
    if not port.isascii() or not port.isdecimal() or not 1024 <= int(port) <= 65535 or int(port) in (9090, 10000):
        raise ValueError('PORT must be an unprivileged ingress port distinct from internal ports.')
    mode = env.get('GATEWAY_TLS_MODE')
    prelude, checks = '', ''
    if mode == 'trusted-edge':
        if env.get('EDGE_TRUST_VERIFIED') != '1':
            raise ValueError('Verified upstream TLS and replacement-header guarantees are required.')
        cidrs = env.get('TRUSTED_EDGE_CIDRS', '').split(',')
        networks = [ip_network(value.strip(), strict=True) for value in cidrs if value.strip()]
        if not networks or any(network.prefixlen == 0 for network in networks):
            raise ValueError('Supply bounded immediate-edge CIDRs; wildcard trust is prohibited.')
        prelude = 'geo $trusted_edge { default 0; ' + ' '.join(f'{network} 1;' for network in networks) + ' }\n'
        checks = '''if ($trusted_edge = 0) { return 444; }
        if ($http_x_forwarded_proto != https) { return 400; }
        if ($http_x_real_ip = "") { return 400; }'''
        client = '$http_x_real_ip'
        listen = f'listen 0.0.0.0:{int(port)};'
        tls = ''
    elif mode == 'direct':
        def path(name):
            value = env.get(name, '')
            if not re.fullmatch(r'/[A-Za-z0-9_./-]+', value):
                raise ValueError('Direct TLS requires safe absolute certificate/key file paths.')
            return value
        tls = f'ssl_certificate {path("GATEWAY_TLS_CERT_FILE")};\nssl_certificate_key {path("GATEWAY_TLS_KEY_FILE")};\nssl_protocols TLSv1.2 TLSv1.3;'
        listen = f'listen 0.0.0.0:{int(port)} ssl;'
        client = '$remote_addr'
    else:
        raise ValueError('Explicit direct or trusted-edge TLS mode is required.')
    proxy = f'''proxy_pass http://127.0.0.1:10000;
        proxy_set_header Host {host};
        proxy_set_header X-Forwarded-For "";
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Dawana-Client-IP {client};
        proxy_set_header Forwarded "";
        proxy_cache off;
        proxy_hide_header Cache-Control;
        add_header Cache-Control "private, no-store" always;
        proxy_read_timeout 60s;'''
    frontend_headers = 'add_header X-Content-Type-Options nosniff always; add_header X-Frame-Options DENY always;'
    return f'''pid /run/dawana/nginx.pid;
error_log /dev/stderr emerg;
worker_processes 1;
events {{ worker_connections 512; }}
http {{
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    log_format private_status '$status $request_time';
    access_log /dev/stdout private_status;
    client_body_temp_path /run/dawana/body;
    proxy_temp_path /run/dawana/proxy;
    fastcgi_temp_path /run/dawana/fastcgi;
    uwsgi_temp_path /run/dawana/uwsgi;
    scgi_temp_path /run/dawana/scgi;
    {prelude}
    server {{
        {listen}
        {tls}
        server_name {host};
        if ($host != {host}) {{ return 444; }}
        {checks}
        root /app/frontend;
        index index.html;
        client_max_body_size 101m;
        location ~ ^/(api|admin|static)(/|$) {{ {proxy} }}
        location ~ ^/(media|health)(/|$) {{ return 404; }}
        location = /_container/live {{ access_log off; add_header Cache-Control no-store; return 200 'gateway-alive'; }}
        location = /_container/ready {{ rewrite ^ /api/v1/health/ break; {proxy} }}
        location ^~ /_container/ {{ return 404; }}
        location /assets/ {{ try_files $uri =404; {frontend_headers} add_header Cache-Control "public, max-age=31536000, immutable"; }}
        location = /index.html {{ {frontend_headers} add_header Cache-Control no-store; }}
        location / {{ {frontend_headers} try_files $uri $uri/ /index.html; }}
    }}
    # Private health socket: no public HTTPS exception and no SPA false positive.
    server {{
        listen 127.0.0.1:9090;
        access_log off;
        location = /_container/live {{ return 200 'gateway-alive'; }}
        location = /_container/ready {{
            proxy_pass http://127.0.0.1:10000/api/v1/health/;
            proxy_set_header Host {host};
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For "";
            proxy_set_header X-Dawana-Client-IP 127.0.0.1;
        }}
        location / {{ return 404; }}
    }}
}}
'''
