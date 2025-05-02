## 异步 SOCKS5→HTTP 代理服务器

   （注意：不支持dns隐匿，上游socket5不要配置远程dns解析！）

一个基于 `asyncio` 和（可选）`uvloop` 的高性能 SOCKS5 代理，流量通过上游 HTTP 代理（如 Burp Suite）转发。

------

### 功能特性

- **异步+uvloop 加速**：利用 `asyncio`，可选 `uvloop` 进一步提升事件循环性能。
- **连接池复用**：重用与上游代理的空闲连接，减少频繁的 TCP 握手。
- **空闲连接回收**：通过 `reap_idle` 定时清理超时或关闭的连接，释放资源。
- **池大小限制**：可配置 `max_idle`，防止过多空闲连接耗尽文件描述符。
- **大缓冲转发**：使用 64 KB 读写块，提升吞吐量，减少上下文切换。
- **简化日志输出**：默认只输出 `WARNING` 及以上级别，降低高并发日志噪声。

------

### 环境要求

- Python 3.8+
- 可选依赖：`uvloop`（推荐在 Linux 上安装，用于加速）

安装命令：

```bash
pip install asyncio
# 可选安装 uvloop：
pip install uvloop
```

------

### 安装与运行

1. 将脚本保存为 `async_socks5_proxy.py`，放入常用工具目录。

2. （可选）确保已安装 `uvloop`。

3. 在命令行运行：

   ```bash
   python async_socks5_proxy.py \
     --socks-host 127.0.0.1 \
     --socks-port 1080 \
     --proxy-host 127.0.0.1 \
     --proxy-port 8080
   ```

**参数说明**：

| 参数           | 含义                            | 默认值      |
| -------------- | ------------------------------- | ----------- |
| `--socks-host` | 本地 SOCKS5 监听地址            | `127.0.0.1` |
| `--socks-port` | 本地 SOCKS5 监听端口            | `1080`      |
| `--proxy-host` | 上游 HTTP 代理地址 (Burp Suite) | 必填        |
| `--proxy-port` | 上游 HTTP 代理端口              | 必填        |

**示例**：

```bash
python async_socks5_proxy.py --proxy-host 127.0.0.1 --proxy-port 8080
# 浏览器或工具配置 socks5://127.0.0.1:1080
```

------

### 配置建议

- **日志级别**：生产环境使用 `WARNING`，调试时可改为 `INFO`。
- **连接池参数**：
  - `max_idle`（空闲连接上限，默认 10）
  - `idle_timeout`（空闲超时时间，默认 300 秒）

修改示例：

```python
connection_pool = ConnectionPool(max_idle=20, idle_timeout=600)
```

------

### 性能优化说明

- **uvloop** 在 Linux 可提供2-3倍的性能提升。
- **增大缓冲**（64KB）减少系统调用次数。
- **合并 `drain()`** 降低事件循环切换开销。

------

### 许可证

MIT License

------

### 致谢

参考了常见 SOCKS5→HTTP 代理模式，并根据高并发场景进行了优化。
