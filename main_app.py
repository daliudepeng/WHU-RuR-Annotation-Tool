import os
import json
from tkinter import Canvas, filedialog, messagebox, font

# 使用 ttkbootstrap 替代 tkinter
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

# --- 全局设计配置 ---
WINDOW_THEME = "sandstone"
MASK_COLOR = (255, 121, 0, 130)  # 温暖的橙色 (RGB + Alpha)
WINDOW_TITLE = "WHU 数据集标注筛选工具"


class AnnotationTool:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("1280x800")
        self.root.minsize(960, 600)

        # --- 数据与状态 ---
        self.sat_dir, self.mask_dir = "", ""
        self.image_files, self.annotations = [], {}
        self.current_index, self.total_images = 0, 0

        # --- UI 控件变量 ---
        self.progress_var = ttk.IntVar()
        self.progress_label_var = ttk.StringVar()
        self.image_id_var = ttk.StringVar()  # 【新增】用于目录下拉菜单的变量
        self.check_vars = {
            1: ttk.BooleanVar(name="漏标噪音"),
            2: ttk.BooleanVar(name="错标噪音"),
            3: ttk.BooleanVar(name="形态不符")
        }
        self.show_mask = True

        # --- 交互式画布状态变量 ---
        self.zoom_level = 1.0
        self.max_zoom = 10.0
        self.min_zoom = 0.1
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.canvas_image_x = 0
        self.canvas_image_y = 0
        self.current_sat_img_orig = None
        self.current_mask_img_orig = None
        self.displayed_photo = None
        self.resize_job = None

        self._setup_ui()
        self._bind_events()
        self.root.after(100, self._load_data_folders)

    def _setup_ui(self):
        # --- 1. 顶部进度条与目录区 ---
        top_frame = ttk.Frame(self.root, padding=(20, 15, 20, 10))
        top_frame.pack(side=TOP, fill=X, expand=False)

        # 【新增】快速跳转标签和下拉菜单
        ttk.Label(top_frame, text="快速跳转:").pack(side=LEFT, padx=(0, 5))
        self.image_selector = ttk.Combobox(top_frame, textvariable=self.image_id_var, state="readonly", width=15)
        self.image_selector.pack(side=LEFT, padx=(0, 20))

        self.progress_label = ttk.Label(top_frame, textvariable=self.progress_label_var)
        self.progress_label.pack(side=RIGHT, padx=(10, 0))
        self.progress_bar = ttk.Progressbar(top_frame, variable=self.progress_var, bootstyle="warning-striped")
        self.progress_bar.pack(side=LEFT, fill=X, expand=True)

        # --- 底部控制区 ---
        bottom_frame = ttk.Frame(self.root, padding=(20, 15, 20, 15))
        bottom_frame.pack(side=BOTTOM, fill=X, expand=False)
        check_frame = ttk.Frame(bottom_frame)
        check_frame.pack(side=LEFT, fill=X, expand=True)
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(side=RIGHT, fill=NONE, expand=False)

        check_labels = ["漏标噪音", "错标噪音", "形态不符"]
        for i, text in enumerate(check_labels, 1):
            cb = ttk.Checkbutton(check_frame, text=f"{text} ({i})", variable=self.check_vars[i],
                                 bootstyle="warning-square-toggle", command=self.save_current_state)
            cb.pack(side=LEFT, padx=(0, 20))

        ttk.Button(button_frame, text="上一张 (←)", command=self.prev_image, bootstyle="outline-secondary", width=12).pack(
            side=LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="下一张 (→)", command=self.next_image, bootstyle="outline-secondary", width=12).pack(
            side=LEFT, padx=(0, 20))
        ttk.Button(button_frame, text="保存并前进", command=self.save_and_next, bootstyle="success", width=14).pack(
            side=LEFT, padx=(0, 20))
        ttk.Button(button_frame, text="导入进度", command=self.import_progress, bootstyle="outline-info", width=10).pack(
            side=LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="导出结果", command=self.export_results, bootstyle="warning", width=10).pack(
            side=LEFT, padx=0)

        # --- 中间图像显示区 ---
        canvas_frame = ttk.Frame(self.root, padding=1, bootstyle="secondary")
        canvas_frame.pack(side=TOP, fill=BOTH, expand=True, padx=20, pady=(5, 10))
        self.canvas = Canvas(canvas_frame, bg="#FFFFFF", bd=0, highlightthickness=0, cursor="arrow")
        self.canvas.pack(fill=BOTH, expand=True)

    def _bind_events(self):
        # 绑定快捷键
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("<space>", lambda e: self.save_and_next())
        self.root.bind("1", lambda e: self.toggle_check(1))
        self.root.bind("2", lambda e: self.toggle_check(2))
        self.root.bind("3", lambda e: self.toggle_check(3))
        self.root.bind("<KeyPress-q>", self.toggle_mask_visibility)

        # 绑定交互事件
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", self._on_mouse_wheel)
        self.canvas.bind("<Button-5>", self._on_mouse_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_pan_end)

        # 【新增】绑定目录选择事件
        self.image_selector.bind("<<ComboboxSelected>>", self._on_image_select)

    # --- 【新增】目录跳转功能 ---
    def _on_image_select(self, event=None):
        selected_id = self.image_id_var.get()
        if selected_id in self.image_files:
            self.current_index = self.image_files.index(selected_id)
            self.load_image_pair()

    # --- 交互式画布核心功能 ---
    def _on_mouse_wheel(self, event):
        if not self.current_sat_img_orig: return
        if event.num == 4 or event.delta > 0:
            zoom_factor = 1.1
        elif event.num == 5 or event.delta < 0:
            zoom_factor = 0.9
        else:
            return
        new_zoom = self.zoom_level * zoom_factor
        if self.min_zoom <= new_zoom <= self.max_zoom:
            mouse_x, mouse_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            self.canvas_image_x = mouse_x - (mouse_x - self.canvas_image_x) * zoom_factor
            self.canvas_image_y = mouse_y - (mouse_y - self.canvas_image_y) * zoom_factor
            self.zoom_level = new_zoom
            self._update_canvas_image()

    def _on_pan_start(self, event):
        self.pan_start_x, self.pan_start_y = event.x, event.y
        self.canvas.config(cursor="fleur")

    def _on_pan_move(self, event):
        dx, dy = event.x - self.pan_start_x, event.y - self.pan_start_y
        self.canvas_image_x += dx
        self.canvas_image_y += dy
        self.pan_start_x, self.pan_start_y = event.x, event.y
        self._update_canvas_image()

    def _on_pan_end(self, event):
        self.canvas.config(cursor="arrow")

    def _reset_view(self):
        if not self.current_sat_img_orig: return
        canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10: return
        img_w, img_h = self.current_sat_img_orig.size
        scale = min(canvas_w / img_w, canvas_h / img_h)
        self.zoom_level = scale
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        self.canvas_image_x = (canvas_w - new_w) / 2
        self.canvas_image_y = (canvas_h - new_h) / 2
        self._update_canvas_image()

    def _update_canvas_image(self):
        if not self.current_sat_img_orig: return
        if self.show_mask and self.current_mask_img_orig:
            processed_mask = self._process_mask(self.current_mask_img_orig, self.current_sat_img_orig.size)
            composite_img = Image.alpha_composite(self.current_sat_img_orig.copy(), processed_mask)
        else:
            composite_img = self.current_sat_img_orig.copy()
        zoomed_size = (int(composite_img.width * self.zoom_level), int(composite_img.height * self.zoom_level))
        if zoomed_size[0] < 1 or zoomed_size[1] < 1: return
        resized_img = composite_img.resize(zoomed_size, Image.Resampling.LANCZOS)
        self.displayed_photo = ImageTk.PhotoImage(resized_img)
        self.canvas.delete("all")
        self.canvas.create_image(self.canvas_image_x, self.canvas_image_y, anchor="nw", image=self.displayed_photo)

    def _on_resize(self, event=None):
        if self.resize_job: self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(250, self._reset_view)

    # --- 智能“断点续传” ---
    def import_progress(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")], title="导入标注进度")
        if not file_path: return
        try:
            new_annotations = {}
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    parts = line.split(',')
                    file_id = parts[0].strip()
                    if not file_id: continue
                    tags = [int(p.strip()) for p in parts[1:] if p.strip()]
                    new_annotations[file_id] = tags
            self.annotations = new_annotations
            messagebox.showinfo("成功", f"进度已成功从\n{file_path}\n导入。")
            resume_index = 0
            if self.annotations and self.image_files:
                for i, file_id in enumerate(self.image_files):
                    if file_id not in self.annotations:
                        resume_index = i
                        break
                else:
                    resume_index = self.total_images - 1
            self.current_index = resume_index
            self.load_image_pair()
        except Exception as e:
            messagebox.showerror("导入失败", f"无法读取或解析文件: {e}\n\n请确保文件格式正确。")

    # --- 其他核心功能函数 ---
    def load_image_pair(self):
        if not self.image_files: return
        file_id = self.image_files[self.current_index]
        sat_filename = next((f for f in os.listdir(self.sat_dir) if f.startswith(file_id)), None)
        mask_filename = next((f for f in os.listdir(self.mask_dir) if f.startswith(file_id)), None)
        if not sat_filename or not mask_filename:
            messagebox.showwarning("文件缺失", f"找不到ID为 {file_id} 的文件。")
            return
        try:
            self.current_sat_img_orig = Image.open(os.path.join(self.sat_dir, sat_filename)).convert("RGBA")
            self.current_mask_img_orig = Image.open(os.path.join(self.mask_dir, mask_filename))
            self._update_ui_state(f"{sat_filename} ({self.current_index + 1}/{self.total_images})")
            self._reset_view()
        except Exception as e:
            messagebox.showerror("图像加载错误", f"加载文件 {file_id} 时出错: {e}")
            self.current_sat_img_orig = self.current_mask_img_orig = None

    def _load_data_folders(self):
        try:
            current_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            current_path = os.getcwd()
        self.sat_dir = os.path.join(current_path, 'sat')
        self.mask_dir = os.path.join(current_path, 'mask')
        if not os.path.isdir(self.sat_dir) or not os.path.isdir(self.mask_dir):
            messagebox.showerror("错误", f"未在程序目录下找到 'sat' 和 'mask' 文件夹！\n\n请确保这两个文件夹与脚本文件位于同一目录。")
            self.root.quit();
            return
        self._pair_files()

    def _pair_files(self):
        sat_files = {f.split('_')[0] for f in os.listdir(self.sat_dir) if f.endswith(('.jpg', '.png', '.tif'))}
        mask_files = {f.split('_')[0] for f in os.listdir(self.mask_dir) if f.endswith(('.jpg', '.png', '.tif'))}
        common_ids = sorted(list(sat_files.intersection(mask_files)))
        if not common_ids:
            messagebox.showerror("错误", "在 'sat' 和 'mask' 文件夹中没有找到匹配的文件。")
            self.root.quit();
            return
        self.image_files = common_ids
        self.total_images = len(self.image_files)
        # 【新增】为目录下拉菜单设置值
        self.image_selector['values'] = self.image_files
        self.progress_bar.config(maximum=self.total_images)
        self.current_index = 0
        self.load_image_pair()

    def _process_mask(self, mask_img, size):
        mask_img = mask_img.convert("L")
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        mask_data = mask_img.load()
        overlay_data = overlay.load()
        for y in range(mask_img.height):
            for x in range(mask_img.width):
                if mask_data[x, y] != 0: overlay_data[x, y] = MASK_COLOR
        return overlay

    def _update_ui_state(self, title_info):
        self.progress_var.set(self.current_index + 1)
        progress_percent = (self.current_index + 1) / self.total_images if self.total_images > 0 else 0
        self.progress_label_var.set(f"{self.current_index + 1} / {self.total_images} ({progress_percent:.1%})")
        self.root.title(f"{WINDOW_TITLE} - {title_info}")
        file_id = self.image_files[self.current_index]
        # 【新增】同步目录下拉菜单的显示
        self.image_id_var.set(file_id)
        annotations = self.annotations.get(file_id, [])
        for i, var in self.check_vars.items(): var.set(i in annotations)

    def save_current_state(self):
        if not self.image_files: return
        file_id = self.image_files[self.current_index]
        self.annotations[file_id] = [k for k, v in self.check_vars.items() if v.get()]

    def next_image(self):
        if self.current_index < self.total_images - 1:
            self.current_index += 1
            self.load_image_pair()

    def prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.load_image_pair()

    def save_and_next(self):
        self.save_current_state()
        self.next_image()

    def toggle_check(self, key):
        self.check_vars[key].set(not self.check_vars[key].get())
        self.save_current_state()

    def toggle_mask_visibility(self, event=None):
        self.show_mask = not self.show_mask
        self._update_canvas_image()

    def export_results(self):
        self.save_current_state()
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="导出标注结果", initialfile="annotations.txt")
        if not file_path: return
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# WHU 数据集标注筛选结果\n# 格式: 文件ID,标签1,标签2,...\n")
                for file_id, tags in sorted(self.annotations.items()):
                    f.write(f"{file_id}{',' if tags else ''}{','.join(map(str, tags))}\n")
            messagebox.showinfo("成功", f"结果已成功导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"无法写入文件: {e}")


if __name__ == "__main__":
    root = ttk.Window(themename=WINDOW_THEME)
    app = AnnotationTool(root)
    root.mainloop()