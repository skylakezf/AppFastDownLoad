"""
App快速下载 - 资源生成脚本（带文件夹监控）
1. 监控网络文件夹 \\QITV1534\共享文件\安装目录\X_FastDownload 的变动
2. 变化时自动同步最新文件到本地 Main 文件夹
3. 同步完成后运行原有的扫描生成逻辑
"""

import os
import json
import base64
import sys
import time
import shutil
import hashlib
from pathlib import Path

# ============================
# 配置区域
# ============================
SOURCE_DIR = r"\\QITV1534\共享文件\安装目录\X_FastDownload"   # 监控的网络文件夹
LOCAL_MAIN_DIR = r"C:\Users\Remote\Desktop\App快速下载\Main"  # 本地同步目标
BASE_DIR = r"C:\Users\Remote\Desktop\App快速下载"              # 脚本工作目录（index.html 所在目录）
DEBOUNCE_SECONDS = 15      # 防抖时间：变化后等待 N 秒，期间无新变化才触发同步
POLL_INTERVAL = 10         # 轮询间隔（秒）
# ============================


def get_base_dir():
    """获取脚本工作目录"""
    return BASE_DIR


def extract_icon_base64(exe_path: str) -> str:
    """
    从 .exe 文件中提取图标，返回 base64 字符串。
    需要 pywin32 库: pip install pywin32
    如果提取失败，返回空字符串。
    """
    try:
        import win32ui
        import win32gui
        import win32con
        import win32api
        from PIL import Image
        import io

        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)

        large, small = win32gui.ExtractIconEx(exe_path, 0)
        if not large and not small:
            return ""

        hicon = large[0] if large else small[0]

        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
        hdc = hdc.CreateCompatibleDC()
        hdc.SelectObject(hbmp)
        hdc.DrawIcon((0, 0), hicon)

        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGBA",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr, "raw", "BGRA", 0, 1
        )

        win32gui.DestroyIcon(hicon)
        hdc.DeleteDC()
        win32gui.DeleteObject(hbmp.GetHandle())

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    except ImportError:
        print("警告: 未安装 pywin32 或 Pillow，无法提取图标。", file=sys.stderr)
        print("      安装命令: pip install pywin32 Pillow", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"警告: 提取图标失败 ({exe_path}): {e}", file=sys.stderr)
        return ""


# 所有支持的文件扩展名
ALL_EXTS = {".exe", ".msi", ".bat", ".cmd", ".zip", ".rar", ".7z", ".reg", ".ps1", ".txt", ".iso"}
MAX_DEPTH = 3  # Main 下最多 3 层子目录


def scan_folder(folder_path: str, current_depth: int, rel_base: str) -> dict:
    """
    递归扫描文件夹，返回树形节点。
    """
    folder_name = os.path.basename(folder_path)
    rel_path = os.path.join(rel_base, folder_name).replace("\\", "/")

    programs = []
    children = []

    try:
        entries = sorted(os.listdir(folder_path))
    except PermissionError:
        entries = []

    for entry in entries:
        if entry.startswith("."):
            continue

        entry_path = os.path.join(folder_path, entry)

        if os.path.isdir(entry_path):
            if current_depth < MAX_DEPTH:
                child_node = scan_folder(entry_path, current_depth + 1, rel_path)
                children.append(child_node)
        else:
            name, ext = os.path.splitext(entry)
            if ext.lower() not in ALL_EXTS:
                continue

            icon_base64 = ""
            if ext.lower() == ".exe":
                icon_base64 = extract_icon_base64(entry_path)

            file_rel_path = os.path.join(rel_base, folder_name, entry).replace("\\", "/")

            programs.append({
                "name": name,
                "fileName": entry,
                "ext": ext.lower(),
                "path": file_rel_path,
                "icon": icon_base64,
                "size": os.path.getsize(entry_path)
            })

    return {
        "name": folder_name,
        "path": rel_path,
        "programs": programs,
        "children": children
    }


def scan_main_folder():
    """遍历 Main 文件夹，返回根节点数组"""
    main_dir = LOCAL_MAIN_DIR

    if not os.path.exists(main_dir):
        print(f"错误: 找不到 Main 文件夹: {main_dir}", file=sys.stderr)
        sys.exit(1)

    root_nodes = []
    for entry in sorted(os.listdir(main_dir)):
        entry_path = os.path.join(main_dir, entry)
        if entry.startswith(".") or not os.path.isdir(entry_path):
            continue

        node = scan_folder(entry_path, current_depth=1, rel_base="Main")
        root_nodes.append(node)

    return root_nodes


def count_all_programs(node: dict) -> int:
    """递归统计节点及其子节点的程序总数"""
    total = len(node.get("programs", []))
    for child in node.get("children", []):
        total += count_all_programs(child)
    return total


def flatten_programs(node: dict) -> list:
    """递归收集节点及其所有子节点的 programs"""
    result = list(node.get("programs", []))
    for child in node.get("children", []):
        result.extend(flatten_programs(child))
    return result


def generate():
    """主入口：扫描并生成 data.js"""
    data = scan_main_folder()

    total_programs = sum(count_all_programs(n) for n in data)
    total_categories = len(data)

    output_file = os.path.join(get_base_dir(), "data.js")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("// 自动生成，请勿手动编辑\n")
        f.write(f"// 一级分类数: {total_categories}, 程序总数: {total_programs}\n")
        f.write(f"// 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("window.APP_DATA = ")
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"✓ 生成完成！")
    print(f"  一级分类数: {total_categories}")
    print(f"  程序总数: {total_programs}")
    print(f"  输出文件: {output_file}")
    print()

    def print_tree(nodes, indent=0):
        for n in nodes:
            prefix = "  " * indent + ("├─ " if indent > 0 else "")
            p_count = count_all_programs(n)
            print(f"{prefix}[{n['name']}] {p_count} 个程序")
            if n.get("children"):
                print_tree(n["children"], indent + 1)

    if data:
        print("目录结构:")
        print_tree(data)


# ============================
# 文件夹同步与监控
# ============================

def compute_dir_snapshot(dir_path: str) -> dict:
    """
    计算文件夹快照：{ 相对路径: (文件大小, 修改时间) }
    用于比对变化。
    """
    snapshot = {}
    if not os.path.exists(dir_path):
        return snapshot

    for root, dirs, files in os.walk(dir_path):
        for f in files:
            abs_path = os.path.join(root, f)
            rel_path = os.path.relpath(abs_path, dir_path)
            try:
                stat = os.stat(abs_path)
                snapshot[rel_path] = (stat.st_size, stat.st_mtime)
            except OSError:
                pass
    return snapshot


def sync_folders(source: str, dest: str):
    """
    将 source 文件夹完全同步到 dest 文件夹。
    使用 robocopy 镜像模式（仅复制变化的文件，删除目标多余文件）。
    如果 robocopy 不可用，回退到 Python shutil。
    """
    if not os.path.exists(source):
        print(f"警告: 源文件夹不存在: {source}")
        return False

    os.makedirs(dest, exist_ok=True)

    # 优先使用 robocopy（Windows 原生，速度快、支持网络路径）
    try:
        import subprocess
        print(f"[同步] {source}")
        print(f"    -> {dest}")
        result = subprocess.run(
            ["robocopy", source, dest, "/MIR", "/R:3", "/W:2", "/NP", "/NDL", "/NFL"],
            capture_output=True, text=True, timeout=300
        )
        # robocopy 返回码 >= 8 表示严重错误
        # 返回码 0-7 都算正常：0=无变化, 1=有复制, 2=有额外文件, 3=2+1, 4=有不匹配, etc.
        if result.returncode >= 8:
            print(f"  robocopy 异常 (返回码 {result.returncode})")
            print(f"  stderr: {result.stderr.strip()}")
            return False
        print(f"  robocopy 完成 (返回码 {result.returncode})")
        return True

    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  robocopy 不可用 ({e})，使用 Python shutil 同步...")
        return _sync_with_shutil(source, dest)


def _sync_with_shutil(source: str, dest: str) -> bool:
    """使用 shutil 进行文件夹同步（fallback 方案）"""
    try:
        # 删除目标中多余的文件/文件夹
        if os.path.exists(dest):
            source_names = set(os.listdir(source)) if os.path.exists(source) else set()
            for item in os.listdir(dest):
                if item not in source_names:
                    item_path = os.path.join(dest, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    else:
                        os.remove(item_path)

        # 复制/更新源文件
        if os.path.exists(source):
            for item in os.listdir(source):
                src_item = os.path.join(source, item)
                dst_item = os.path.join(dest, item)

                if os.path.isdir(src_item):
                    if not os.path.exists(dst_item):
                        shutil.copytree(src_item, dst_item)
                    else:
                        _sync_with_shutil(src_item, dst_item)
                else:
                    # 仅当源文件更新时才复制
                    need_copy = True
                    if os.path.exists(dst_item):
                        src_stat = os.stat(src_item)
                        dst_stat = os.stat(dst_item)
                        need_copy = (src_stat.st_size != dst_stat.st_size or
                                     src_stat.st_mtime > dst_stat.st_mtime)
                    if need_copy:
                        shutil.copy2(src_item, dst_item)

        return True
    except Exception as e:
        print(f"  shutil 同步失败: {e}", file=sys.stderr)
        return False


def monitor_and_sync():
    """
    持续监控网络文件夹，变化时自动同步并重新生成。
    使用轮询方式（不依赖第三方库），兼容性好。
    """
    print("=" * 60)
    print("App快速下载 - 文件夹监控与生成脚本")
    print("=" * 60)
    print(f"监控源:   {SOURCE_DIR}")
    print(f"同步目标: {LOCAL_MAIN_DIR}")
    print(f"轮询间隔: {POLL_INTERVAL} 秒")
    print(f"防抖时间: {DEBOUNCE_SECONDS} 秒")
    print("=" * 60)
    print()

    # 1. 首次同步
    print("[启动] 执行首次同步...")
    if sync_folders(SOURCE_DIR, LOCAL_MAIN_DIR):
        print("[启动] 首次同步完成，运行生成逻辑...")
        try:
            generate()
        except Exception as e:
            print(f"生成失败: {e}", file=sys.stderr)
    print()

    # 2. 持续监控
    print("[监控] 开始监控文件夹变化...")
    last_snapshot = compute_dir_snapshot(SOURCE_DIR)
    last_change_time = time.time()
    sync_triggered = False

    while True:
        try:
            time.sleep(POLL_INTERVAL)

            # 检查源文件夹是否存在
            if not os.path.exists(SOURCE_DIR):
                print(f"[监控] 源文件夹不可访问，等待重试...")
                continue

            # 获取当前快照
            current_snapshot = compute_dir_snapshot(SOURCE_DIR)

            # 比对变化
            has_changed = False
            change_details = []

            # 检查新增和修改
            for path, (size, mtime) in current_snapshot.items():
                if path not in last_snapshot:
                    has_changed = True
                    change_details.append(f"  + 新增: {path}")
                elif last_snapshot[path] != (size, mtime):
                    has_changed = True
                    change_details.append(f"  * 修改: {path}")

            # 检查删除
            for path in last_snapshot:
                if path not in current_snapshot:
                    has_changed = True
                    change_details.append(f"  - 删除: {path}")

            # 更新快照
            last_snapshot = current_snapshot

            if has_changed:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{timestamp}] 检测到变化:")
                for detail in change_details:
                    print(detail)
                last_change_time = time.time()
                sync_triggered = False  # 重置，等待防抖
            else:
                # 无变化，检查是否需要触发同步（防抖结束）
                if not sync_triggered and (time.time() - last_change_time) >= DEBOUNCE_SECONDS:
                    # 检查 last_snapshot 是否有内容，避免刚启动就触发
                    if last_snapshot:
                        sync_triggered = True
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        print(f"\n[{timestamp}] 变化稳定，开始同步...")
                        if sync_folders(SOURCE_DIR, LOCAL_MAIN_DIR):
                            print(f"[{timestamp}] 同步完成，运行生成逻辑...")
                            try:
                                generate()
                            except Exception as e:
                                print(f"生成失败: {e}", file=sys.stderr)

        except KeyboardInterrupt:
            print("\n[退出] 用户中断，脚本退出。")
            break
        except Exception as e:
            print(f"[错误] {e}", file=sys.stderr)
            time.sleep(POLL_INTERVAL * 2)


# ============================
# 主入口
# ============================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="App快速下载 - 文件夹监控与生成脚本")
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅执行一次同步+生成，不进入监控模式"
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="仅运行生成逻辑（不监控、不同步）"
    )
    args = parser.parse_args()

    if args.generate_only:
        # 仅生成模式（等同于原有逻辑）
        generate()
    elif args.once:
        # 单次模式：同步 + 生成
        print("单次同步模式：")
        if sync_folders(SOURCE_DIR, LOCAL_MAIN_DIR):
            generate()
    else:
        # 默认：持续监控模式
        monitor_and_sync()
