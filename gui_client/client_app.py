import tkinter as tk
from tkinter import filedialog, scrolledtext
from PIL import Image, ImageTk
import requests
import io

# Địa chỉ của Docker Server (đang chạy trên chính máy này)
SERVER_URL = "http://localhost:8000/predict"

class CCCDReaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Công cụ đọc CCCD (Client)")
        self.root.geometry("800x600")
        
        self.image_path = None

        # --- Giao diện ---
        # Khung bên trái (Ảnh) và phải (Kết quả)
        left_frame = tk.Frame(root, width=400, height=600, bg='gray')
        left_frame.pack(side="left", fill="both", expand=True)
        
        right_frame = tk.Frame(root, width=400, height=600)
        right_frame.pack(side="right", fill="both", expand=True)

        # Nút chọn ảnh
        self.btn_select = tk.Button(left_frame, text="1. Chọn ảnh CCCD", command=self.select_image, height=2, bg="lightblue")
        self.btn_select.pack(pady=10, fill="x", padx=20)

        # Vùng hiển thị ảnh
        self.lbl_image = tk.Label(left_frame, text="Chưa có ảnh")
        self.lbl_image.pack(pady=10, expand=True)

        # Nút xử lý
        self.btn_process = tk.Button(right_frame, text="2. Đọc thông tin (Gửi lên Docker)", command=self.process_image, height=2, bg="lightgreen", state="disabled")
        self.btn_process.pack(pady=10, fill="x", padx=20)
        
        # Vùng hiển thị kết quả
        tk.Label(right_frame, text="Kết quả đọc được:").pack(anchor="w", padx=20)
        self.txt_result = scrolledtext.ScrolledText(right_frame, width=40, height=25)
        self.txt_result.pack(padx=20, pady=10, fill="both", expand=True)

    def select_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if file_path:
            self.image_path = file_path
            self.show_image(file_path)
            self.btn_process.config(state="normal")
            self.txt_result.delete(1.0, tk.END)
            self.txt_result.insert(tk.END, "Đã chọn ảnh. Nhấn nút xử lý.")

    def show_image(self, path):
        img = Image.open(path)
        img.thumbnail((350, 350)) # Thu nhỏ để vừa giao diện
        img_tk = ImageTk.PhotoImage(img)
        self.lbl_image.config(image=img_tk, text="")
        self.lbl_image.image = img_tk

    def process_image(self):
        if not self.image_path:
            return
        
        self.txt_result.delete(1.0, tk.END)
        self.txt_result.insert(tk.END, "Đang gửi ảnh lên Docker Server và xử lý...\nVui lòng chờ (lần đầu sẽ hơi lâu do Docker tải model)...")
        self.root.update()

        try:
            # Gửi file ảnh lên Server
            with open(self.image_path, 'rb') as f:
                files = {'file': (self.image_path, f, 'image/jpeg')}
                response = requests.post(SERVER_URL, files=files, timeout=60) # Timeout 60s
            
            if response.status_code == 200:
                data = response.json().get("data", [])
                result_text = "\n--- THÔNG TIN ĐỌC ĐƯỢC ---\n\n"
                for line in data:
                    result_text += line + "\n"
                self.txt_result.delete(1.0, tk.END)
                self.txt_result.insert(tk.END, result_text)
            else:
                self.txt_result.insert(tk.END, f"\nLỗi Server: {response.status_code} - {response.text}")

        except requests.exceptions.ConnectionError:
             self.txt_result.insert(tk.END, "\nLỗi: Không thể kết nối đến Docker Server.\nHãy đảm bảo bạn đã chạy container Docker (Bước 1).")
        except Exception as e:
             self.txt_result.insert(tk.END, f"\nĐã xảy ra lỗi: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = CCCDReaderApp(root)
    root.mainloop()