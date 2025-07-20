import requests
from bs4 import BeautifulSoup
import re
import os
import subprocess
import platform

# --- Configuration ---
# 目标URL列表
URLS = ['https://api.uouin.com/cloudflare.html',
        'https://ip.164746.xyz']
# 正则表达式用于匹配IP地址
IP_PATTERN = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
# 输出文件名
OUTPUT_FILE = 'ip.txt'
# 最大IP数量
MAX_IPS = 10
# 最大延迟 (ms)
MAX_LATENCY_MS = 350
# 最小下载速度 (MB/s)
MIN_SPEED_MBPS = 20
# 测速文件URL和主机 (10MB file)
SPEED_TEST_URL = 'https://speed.cloudflare.com/__down?bytes=10000000'
SPEED_TEST_HOST = 'speed.cloudflare.com'

# --- Helper Functions ---

def check_latency(ip):
    """Pings an IP to check its latency. Returns latency in ms or None if it fails/times out."""
    try:
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', '-w', '1000', ip]  # 1 packet, 1s timeout
        result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)

        if result.returncode != 0:
            return None

        output = result.stdout
        if platform.system().lower() == 'windows':
            # Try to find 'Average = Xms' or just 'Xms' at the end of a line for different language outputs
            match = re.search(r'Average = (\d+)ms', output) or re.search(r'(\d+)ms$', output, re.MULTILINE)
            if match:
                # When both patterns match, groups() will contain both captures, with one being None.
                # We filter out the None and take the first valid group.
                valid_groups = [g for g in match.groups() if g is not None]
                if valid_groups:
                    return int(valid_groups[0])
        else:  # Linux/macOS
            match = re.search(r'rtt min/avg/max/mdev = .*?/(\d+\.\d+)/', output)
            if match:
                return float(match.group(1))
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

def check_speed(ip):
    """Measures download speed from an IP. Returns speed in MB/s or None."""
    try:
        command = [
            'curl', '--resolve', f'{SPEED_TEST_HOST}:443:{ip}',
            '-o', os.devnull, '-w', '%{speed_download}',
            '--silent', '--connect-timeout', '5', '--max-time', '15',
            SPEED_TEST_URL
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)

        if result.returncode != 0:
            return None
            
        speed_bytes_per_sec = float(result.stdout)
        if speed_bytes_per_sec == 0:
            return None
            
        speed_MBps = speed_bytes_per_sec / (1024 * 1024)
        return speed_MBps
        
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None

# --- Main Script ---

def main():
    """Main function to collect and filter IPs."""
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    collected_ips_set = set()
    ip_count = 0

    print("开始收集并筛选IP...")

    for url in URLS:
        if ip_count >= MAX_IPS:
            break
        
        print(f"正在从 {url} 获取IP...")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  -> 获取失败: {e}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        
        elements = soup.find_all('tr')
        
        page_ips = []
        for element in elements:
            element_text = element.get_text()
            ip_matches = re.findall(IP_PATTERN, element_text)
            page_ips.extend(ip_matches)

        unique_ips = sorted(list(set(page_ips)))
        print(f"  -> 在 {url} 找到 {len(unique_ips)} 个独立IP。开始测试...")

        for ip in unique_ips:
            if ip_count >= MAX_IPS:
                print(f"已达到 {MAX_IPS} 个IP的限制，停止测试。")
                break
            
            if ip in collected_ips_set:
                continue
            
            collected_ips_set.add(ip)

            print(f"  -> 正在测试 IP: {ip}")
            latency = check_latency(ip)
            if latency is None or latency > MAX_LATENCY_MS:
                print(f"    - 延迟测试失败 ({(latency or 'N/A')}ms > {MAX_LATENCY_MS}ms).")
                continue
            print(f"    - 延迟测试通过: {latency:.2f}ms")

            speed = check_speed(ip)
            if speed is None or speed < MIN_SPEED_MBPS:
                print(f"    - 速度测试失败 ({(speed or 0):.2f}MB/s < {MIN_SPEED_MBPS}MB/s).")
                continue
            print(f"    - 速度测试通过: {speed:.2f}MB/s")

            print(f"  -> 成功: IP {ip} 符合所有要求，已保存。")
            with open(OUTPUT_FILE, 'a') as file:
                file.write(ip + '\n')
            ip_count += 1
            
    print(f"\n完成。总共找到 {ip_count} 个符合要求的IP。")
    print(f"结果已保存到 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()