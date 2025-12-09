import sys
import csv
import json
import os
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QTableView, QHeaderView, QPushButton,
    QDialog, QDateTimeEdit, QLabel, QMessageBox,
    QFileDialog
)
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QDateTime,
    QSortFilterProxyModel
)
from PyQt6.QtGui import QFont, QColor

# =========================
#  加载 QSS 样式（除表格外）
# =========================
QSS_TEMPLATE_PATH = Path(__file__).parent / 'PyQt6 可复用 QSS 样式模板.md'
if QSS_TEMPLATE_PATH.exists():
    with open(QSS_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        QSS = f.read()
else:
    QSS = ""

# =========================
#  常量定义
# =========================
PROVINCE_MAP = {
    "CN-AH": "安徽", "CN-BJ": "北京", "CN-CQ": "重庆", "CN-FJ": "福建",
    "CN-GD": "广东", "CN-GS": "甘肃", "CN-GX": "广西", "CN-GZ": "贵州",
    "CN-HA": "河南", "CN-HB": "湖北", "CN-HE": "河北", "CN-HI": "海南",
    "CN-HK": "香港", "CN-HL": "黑龙江", "CN-HN": "湖南", "CN-JL": "吉林",
    "CN-JS": "江苏", "CN-JX": "江西", "CN-LN": "辽宁", "CN-MO": "澳门",
    "CN-NM": "内蒙古", "CN-NX": "宁夏", "CN-QH": "青海", "CN-SC": "四川",
    "CN-SD": "山东", "CN-SH": "上海", "CN-SN": "陕西", "CN-SX": "山西",
    "CN-TJ": "天津", "CN-TW": "台湾", "CN-XJ": "新疆", "CN-XZ": "西藏",
    "CN-YN": "云南", "CN-ZJ": "浙江"
}

PARKS_DATA_FILE = "parks_data.json"
CONFIG_FILE = "config.json"


def get_park_number_int(reference):
    match = re.search(r'-(\\d+)', reference)
    return int(match.group(1)) if match else 0


# =========================
# 激活时间输入对话框
# =========================
class ActivationDialog(QDialog):
    def __init__(self, park_ref, park_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("记录公园激活")
        self.park_ref = park_ref
        self.park_name = park_name
        self.activation_time = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.setStyleSheet(QSS)
        layout.addWidget(QLabel(f"<b>记录激活:</b> {self.park_name} ({self.park_ref})"))
        layout.addWidget(QLabel("选择激活日期:"))

        self.datetime_edit = QDateTimeEdit(self)
        self.datetime_edit.setDateTime(QDateTime.currentDateTime())
        self.datetime_edit.setDisplayFormat("yyyy-MM-dd")
        self.datetime_edit.setCalendarPopup(True)
        layout.addWidget(self.datetime_edit)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        ok_btn = QPushButton("确认激活")
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self.accept_activation)
        btn_layout.addStretch(1)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def accept_activation(self):
        self.activation_time = self.datetime_edit.date().toString("yyyy-MM-dd")
        self.accept()


# =========================
# 数据模型
# =========================
class ParkTableModel(QAbstractTableModel):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self._data = data
        self.header_labels = ["序号", "公园编号", "公园名称", "激活日期 / 操作"]

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.header_labels)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        park = self._data[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(row + 1)
            elif col == 1:
                return park['reference']
            elif col == 2:
                return park['name']
            elif col == 3:
                return park['activation_time'] if park['activated'] else "激活"

        elif role == Qt.ItemDataRole.UserRole:
            return get_park_number_int(park['reference'])

        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.header_labels[section]
        return None

    def update_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()


# =========================
# 代理模型：行高亮
# =========================
class ParkSortingProxyModel(QSortFilterProxyModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        source_index = self.mapToSource(index)
        source_model = self.sourceModel()
        if index.column() == 0 and role == Qt.ItemDataRole.DisplayRole:
            return str(index.row() + 1)
        if role == Qt.ItemDataRole.BackgroundRole:
            if source_index.row() >= len(source_model._data):
                return None
            park = source_model._data[source_index.row()]
            if park.get('activated', False):
                return QColor("#D1FAE5")
        return super().data(index, role)


# =========================
# 主程序窗口
# =========================
class PotaLogbookApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("POTA 公园激活记录")
        self.setGeometry(100, 100, 1000, 600)
        self.setStyleSheet(QSS)
        self.all_parks = []
        self.config = self.load_config()
        self.load_parks_from_json()
        self.setup_ui()
        self.restore_last_province()
        self.filter_parks()

    # ---- 配置加载与保存 ----
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    # ---- 数据加载与保存 ----
    def load_parks_from_json(self):
        if os.path.exists(PARKS_DATA_FILE):
            with open(PARKS_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.all_parks = data

    def save_parks_to_json(self):
        with open(PARKS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.all_parks, f, ensure_ascii=False, indent=4)

    # ---- UI 初始化 ----
    def setup_ui(self):
        cw = QWidget()
        cw.setObjectName("CentralWidget")
        self.setCentralWidget(cw)
        layout = QVBoxLayout(cw)

        hl = QHBoxLayout()
        hl.addWidget(QLabel("<b>选择省份:</b>"))
        self.province_combo = QComboBox()
        self.province_combo.addItem("全部省份", userData=None)
        for code, name in sorted(PROVINCE_MAP.items(), key=lambda x: x[1]):
            self.province_combo.addItem(f"{name} ({code})", userData=code)
        self.province_combo.currentIndexChanged.connect(self.filter_parks)
        hl.addWidget(self.province_combo)

        import_btn = QPushButton("导入 CSV 文件")
        import_btn.clicked.connect(self.import_csv_action)
        hl.addWidget(import_btn)
        hl.addStretch(1)
        layout.addLayout(hl)

        self.park_table_model = ParkTableModel([], self)
        self.proxy_model = ParkSortingProxyModel(self)
        self.proxy_model.setSourceModel(self.park_table_model)
        self.proxy_model.setSortRole(Qt.ItemDataRole.UserRole)

        self.park_table_view = QTableView()
        self.park_table_view.setModel(self.proxy_model)
        self.park_table_view.setSortingEnabled(True)
        self.park_table_view.setAlternatingRowColors(True)
        self.park_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.park_table_view)

    def restore_last_province(self):
        """恢复上次选择的省份"""
        last_code = self.config.get("last_province_code")
        if last_code:
            idx = self.province_combo.findData(last_code)
            if idx >= 0:
                self.province_combo.setCurrentIndex(idx)

    # ---- 数据筛选与刷新 ----
    def filter_parks(self):
        code = self.province_combo.currentData()
        self.config["last_province_code"] = code
        self.save_config()
        parks = self.all_parks if code is None else [p for p in self.all_parks if code in p['provinces']]
        self.park_table_model.update_data(parks)
        self.update_activation_buttons()

    # ---- CSV 导入 ----
    def import_csv_action(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择 POTA 公园 CSV 文件", "", "CSV Files (*.csv)")
        if filename:
            # 调用导入逻辑并获取处理的公园数量
            park_count = self.load_parks_from_csv(filename)
            self.save_parks_to_json()
            self.filter_parks()
            
            # 导入完成后显示成功提示
            QMessageBox.information(
                self, 
                "导入成功", 
                f"成功导入/更新了 {park_count} 个公园记录。"
            )

    def load_parks_from_csv(self, filename):
        existing = {p['reference']: p for p in self.all_parks}
        new_list = []
        processed_count = 0 # 记录处理的公园数量
        with open(filename, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ref, name, desc = row.get('reference'), row.get('name'), row.get('locationDesc')
                if not ref or not name or not desc:
                    continue
                provinces = [c.strip() for c in desc.split(',') if c.strip() in PROVINCE_MAP]
                exist = existing.get(ref, {})
                new_list.append({
                    'reference': ref,
                    'name': name,
                    'provinces': provinces,
                    'activated': exist.get('activated', False),
                    'activation_time': exist.get('activation_time', None)
                })
                processed_count += 1 # 增加计数
        self.all_parks = new_list
        return processed_count # 返回处理的公园数量

    # ---- 激活功能 ----
    def update_activation_buttons(self):
        for row in range(self.proxy_model.rowCount()):
            idx = self.proxy_model.index(row, 3)
            park = self.proxy_model.sourceModel()._data[self.proxy_model.mapToSource(idx).row()]
            if not park.get('activated', False):
                btn = QPushButton("激活")
                btn.clicked.connect(lambda checked=False, ref=park['reference']: self.prompt_activation(ref))
                self.park_table_view.setIndexWidget(idx, btn)
            else:
                self.park_table_view.setIndexWidget(idx, None)

    def prompt_activation(self, park_ref):
        park = next((p for p in self.all_parks if p['reference'] == park_ref), None)
        if not park:
            QMessageBox.warning(self, "错误", f"未找到公园 {park_ref}")
            return
        dlg = ActivationDialog(park_ref, park['name'], self)
        if dlg.exec():
            park['activated'] = True
            park['activation_time'] = dlg.activation_time
            self.save_parks_to_json()
            self.filter_parks()
            QMessageBox.information(self, "成功", f"公园 {park_ref} 已激活：{dlg.activation_time}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))
    w = PotaLogbookApp()
    w.show()
    sys.exit(app.exec())