import http.server
import socketserver
import threading

import webview

PORT = 8000
DIRECTORY = "dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)


def start_server():
    # 绑 "" 等于绑所有网卡：这个壳只是给本机 webview 窗口喂 dist/ 静态文件
    # （下面 url= 用的就是 localhost），局域网里任何人都能把它当文件浏览器读。
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()


threading.Thread(target=start_server).start()

webview.create_window(
    title="Naga Agent",
    url=f"http://localhost:{PORT}",
    min_size=(1200, 800),
)

webview.start()
