import streamlit as st
import pandas as pd
import warnings
import re
import numpy as np
import unidecode
import phonenumbers as pn
from rapidfuzz import fuzz
from geopy import distance
from geopy.distance import geodesic
from tqdm import tqdm
from PIL import Image
warnings.filterwarnings('ignore')

def read_file():
    Province = pd.read_excel("Province.xlsx")
    teleco1 = pd.read_excel("Teleco Master 202307.xlsx", sheet_name='Di động')
    teleco2= pd.read_excel("Teleco Master 202307.xlsx", sheet_name='Cố định')
    OptionalText = pd.read_excel("Op_Add.xlsx")
    text_remove = pd.read_excel("remove_list_hvn.xlsx")        
    text_remove_2 = pd.read_excel("remove_list_vigo.xlsx")
    remove_name = pd.read_excel("remove_listname_hvn.xlsx")
    remove_name_2 = pd.read_excel("remove_listname_vigo.xlsx")

    return Province, teleco1, teleco2, OptionalText, text_remove, text_remove_2, remove_name, remove_name_2

# Xem coi có nằm trong giới hạn vùng lãnh thổ của Việt Nam
def xet_latlng(HVN):
    min_lat, max_lat = 8.18, 23.39
    min_lon, max_lon = 102.14, 109.46

    # Lọc các dòng không nằm trong khu vực của Việt Nam
    filtered_HVN = HVN[
        ~((min_lat <= HVN['Latitude']) & (HVN['Latitude'] <= max_lat) &
        (min_lon <= HVN['Longitude']) & (HVN['Longitude'] <= max_lon))
    ]

    # Lấy ra những HVN mà OutletID không nằm trong filtered_HVN
    unfiltered_outlets = HVN[~HVN['OutletID'].isin(filtered_HVN['OutletID'])]

    return unfiltered_outlets

# Hàm để chuẩn hóa và xóa dấu cách dư thừa, xóa dấu diacritics
def normalize_and_remove_accents(df, columns):
    from unidecode import unidecode
    for col in columns:
        df[col] = df[col].apply(lambda x: unidecode(x).lower().strip() if pd.notna(x) else x)
    return df

# Xét phân cấp thánh phố, huyện, xã và thị trấn
def xet_phancap(hvn_df, province_df):
    hvn_df['WardName'].fillna('', inplace=True)
    hvn_df['WardName'].replace({None: ''}, inplace=True)
    hvn_df['WardName'].replace({'NULL': ''}, inplace=True)

    hvn_df['CustomerAddress'].replace({'NULL': ''}, inplace=True)
    hvn_df['CustomerAddress'].replace({None: ''}, inplace=True)
    hvn_df['CustomerAddress'].replace({'NULL': ''}, inplace=True)

    hvn_df['DistrictName'].replace({'NULL': ''}, inplace=True)
    hvn_df['DistrictName'].replace({None: ''}, inplace=True)
    hvn_df['DistrictName'].replace({'NULL': ''}, inplace=True)

    # Chuẩn hóa và xóa dấu cách dư thừa cho các cột cần thiết trong hvn_df
    hvn_df[['ProvinceName', 'DistrictName', 'WardName']] = normalize_and_remove_accents(hvn_df[['ProvinceName', 'DistrictName', 'WardName']], ['ProvinceName', 'DistrictName', 'WardName'])

    # Chuẩn hóa và xóa dấu cách dư thừa, xóa dấu diacritics cho các cột cần thiết trong province_df
    province_df[['Tỉnh Thành Phố', 'Quận Huyện', 'Phường Xã']] = normalize_and_remove_accents(province_df[['Tỉnh Thành Phố', 'Quận Huyện', 'Phường Xã']], ['Tỉnh Thành Phố', 'Quận Huyện', 'Phường Xã'])

    # Tạo list để lưu thông tin các hvn_outlet_id không khớp
    invalid_outlets_data = []

    # Tìm các HVN_OutletID có ProvinceName không nằm trong danh sách của Province
    for index, row in hvn_df.iterrows():
        hvn_outlet_id = row['OutletID']
        province_name = row['ProvinceName']
        district_name = row['DistrictName']
        ward_name = row['WardName']

        # Kiểm tra xem ProvinceName có trong danh sách của Province không
        if province_name in province_df['Tỉnh Thành Phố'].values:
            # Kiểm tra xem DistrictName có khớp với ['Quận Huyện'] tại ['Tỉnh Thành Phố'] không
            province_row = province_df[province_df['Tỉnh Thành Phố'] == province_name]
            if district_name not in province_row['Quận Huyện'].values:
                invalid_outlets_data.append(row.to_dict())
            else:
                ward_row = province_row[province_row['Quận Huyện'] == district_name]
                if ward_name not in ward_row['Phường Xã'].values:
                    invalid_outlets_data.append(row.to_dict())

        else:
            invalid_outlets_data.append(row.to_dict())

    # Tạo DataFrame từ list thông tin các hvn_outlet_id không khớp
    invalid_outlets_df = pd.DataFrame(invalid_outlets_data)

    return invalid_outlets_df

#clean phone numbers
def clean_phone_data(orig_phone):
    try:
        new_phone = pn.format_number(pn.parse(orig_phone, 'VN'), pn.PhoneNumberFormat.E164)
    except: # NumberParseException
        return 'nophonedata'
    return new_phone

# remove phone numbers beginning with 12345, 012345
def remove_invalid_phone(df_column):
    for num in df_column:
        for s_rm in ['12345', '012345']:
              if num.startswith(s_rm):
                  new_num = '0'
                  df_column = df_column.replace([num], new_num)
    return df_column

def xuly_phone(HVN, Vigo):
    HVN['Phone'] = HVN['Phone'].apply(lambda x: str(x) if type(x) is not str else x)
    Vigo['Phone'] = Vigo['Phone'].apply(lambda x: str(x) if type(x) is not str else x)

    HVN['Phone'] = remove_invalid_phone(HVN['Phone'])
    Vigo['Phone'] = remove_invalid_phone(Vigo['Phone'])

    HVN['Phone']= HVN['Phone'].apply(clean_phone_data)
    Vigo['Phone'] = Vigo['Phone'].apply(clean_phone_data)

    HVN['Phone'] = HVN['Phone'].apply(lambda x: x.replace(' ', ''))
    Vigo['Phone'] = Vigo['Phone'].apply(lambda x: x.replace(' ', ''))

    HVN_nophone = HVN[HVN['Phone'] == 'nophonedata'].copy()
    HVN_phone = HVN.loc[lambda df: ~df.OutletID.isin(HVN_nophone['OutletID'])]

    Vigo_nophone = Vigo[Vigo['Phone'] == 'nophonedata'].copy()
    Vigo_phone = Vigo.loc[lambda df: ~df.OutletID.isin(Vigo_nophone['OutletID'])]

    # Thay thế các số điện thoại bắt đầu bằng "+84" thành "0" trong cột 'Phone'
    HVN_phone['Phone'] = HVN_phone['Phone'].replace(to_replace=r'^\+84', value='0', regex=True)

    # In ra DataFrame sau khi thay đổi
    # print(HVN_phone['Phone'].value_counts())

    # Loại bỏ giá trị trùng lặp từ cột 'Phone'
    HVN_phone['Phone'] = HVN_phone['Phone'].drop_duplicates()
    HVN_phone_na = HVN_phone[HVN_phone['Phone'].isna()]
    HVN_phone_notna = HVN_phone.dropna(subset=['Phone'])

    Vigo_phone['Phone'] = Vigo_phone['Phone'].replace(to_replace=r'^\+84', value='0', regex=True)
    Vigo_phone['Phone'] = Vigo_phone['Phone'].drop_duplicates()
    Vigo_phone_na = Vigo_phone[Vigo_phone['Phone'].isna()]
    Vigo_phone_notna = Vigo_phone.dropna(subset=['Phone'])

    return HVN_nophone, Vigo_nophone, HVN_phone_na, HVN_phone_notna, Vigo_phone_na, Vigo_phone_notna

def xuly_phone_motfile(HVN):
    HVN['Phone'] = HVN['Phone'].apply(lambda x: str(x) if type(x) is not str else x)
    HVN['Phone'] = remove_invalid_phone(HVN['Phone'])
    HVN['Phone']= HVN['Phone'].apply(clean_phone_data)
    HVN['Phone'] = HVN['Phone'].apply(lambda x: x.replace(' ', ''))
    HVN_nophone = HVN[HVN['Phone'] == 'nophonedata'].copy()
    HVN_phone = HVN.loc[lambda df: ~df.OutletID.isin(HVN_nophone['OutletID'])]
    HVN_phone['Phone'] = HVN_phone['Phone'].replace(to_replace=r'^\+84', value='0', regex=True)
    HVN_phone['Phone'] = HVN_phone['Phone'].drop_duplicates()
    HVN_phone_na = HVN_phone[HVN_phone['Phone'].isna()]
    HVN_phone_notna = HVN_phone.dropna(subset=['Phone'])

    return HVN_nophone, HVN_phone_na, HVN_phone_notna

def check_dausomoi(HVN_phone_notna, teleco1):
    matched_rows = []
    not_matching_rows = []

    # Iterate through each row in HVN_phone_notna['Phone']
    for index, phone_number in HVN_phone_notna['Phone'].items():
        match_found = False

        # Check for match in Đầu Số Mới
        for teleco1_prefix_moi in teleco1['Đầu Số Mới']:
            prefix_length = len(str(teleco1_prefix_moi))
            prefix = str(phone_number)[:prefix_length]
            condition_moi = str(teleco1_prefix_moi).startswith(prefix)

            if condition_moi:
                match_found = True
                break

        # Check for match in Đầu Số Cũ if not found in Đầu Số Mới
        if not match_found:
            for teleco1_prefix_cu in teleco1['Đầu Số Cũ']:
                prefix_length_cu = len(str(teleco1_prefix_cu))
                prefix_cu = str(phone_number)[:prefix_length_cu]
                condition_cu = str(teleco1_prefix_cu).startswith(prefix_cu)

                if condition_cu:
                    match_found = True

                    # Update the phone number in HVN_phone_notna['Phone']
                    matching_row_cu = teleco1.loc[teleco1['Đầu Số Cũ'] == teleco1_prefix_cu, 'Đầu Số Mới']
                    new_prefix_cu = matching_row_cu.iloc[0]
                    new_phone_number_cu = new_prefix_cu + str(phone_number)[prefix_length_cu:]
                    HVN_phone_notna.at[index, 'Phone'] = new_phone_number_cu

                    break

        # Add the row to the appropriate list based on match_found
        if match_found:
            matched_rows.append(HVN_phone_notna.loc[index])
        else:
            not_matching_rows.append(HVN_phone_notna.loc[index])

    # Create the DataFrames
    matched_df = pd.DataFrame(matched_rows, columns=HVN_phone_notna.columns)
    not_matching_df = pd.DataFrame(not_matching_rows, columns=HVN_phone_notna.columns)
    
    return matched_df, not_matching_df

def check_mavungmoi(HVN_phone_notna_2, teleco2):
    # Clear any existing rows in matched_df_2 and not_matching_df_2
    matched_rows_2 = []
    not_matching_rows_2 = []

    # Iterate through each row in HVN_phone_notna_2['Phone']
    for index, phone_number in HVN_phone_notna_2['Phone'].items():
        match_found = False

        # Check for match in 'Mã vùng điện thoại mới\t'
        for teleco2_prefix_moi in teleco2['Mã vùng điện thoại mới\t']:
            prefix_length = len(str(teleco2_prefix_moi))
            prefix = str(phone_number)[:prefix_length]
            condition_moi = str(teleco2_prefix_moi).startswith(prefix)

            if condition_moi:
                match_found = True
                break

        # Check for match in 'Mã vùng điện thoại cũ\t' if not found in 'Mã vùng điện thoại mới\t'
        if not match_found:
            for teleco2_prefix_cu in teleco2['Mã vùng điện thoại cũ\t']:
                prefix_length_cu = len(str(teleco2_prefix_cu))
                prefix_cu = str(phone_number)[:prefix_length_cu]
                condition_cu = str(teleco2_prefix_cu).startswith(prefix_cu)

                if condition_cu:
                    match_found = True

                    # Update the phone number in HVN_phone_notna_2['Phone']
                    matching_row_cu = teleco2.loc[teleco2['Mã vùng điện thoại cũ\t'] == teleco2_prefix_cu, 'Mã vùng điện thoại mới\t']
                    new_prefix_cu = matching_row_cu.iloc[0]
                    new_phone_number_cu = new_prefix_cu + str(phone_number)[prefix_length_cu:]
                    HVN_phone_notna_2.at[index, 'Phone'] = new_phone_number_cu

                    break

        # Add the row to the appropriate list based on match_found
        if match_found:
            matched_rows_2.append(HVN_phone_notna_2.loc[index])
        else:
            not_matching_rows_2.append(HVN_phone_notna_2.loc[index])

    # Create the DataFrames
    matched_df_2 = pd.DataFrame(matched_rows_2, columns=HVN_phone_notna_2.columns)
    not_matching_df_2 = pd.DataFrame(not_matching_rows_2, columns=HVN_phone_notna_2.columns)

    return matched_df_2, not_matching_df_2

def tao_danh_sach_thoa_khongthoa(teleco1, teleco2, HVN_phone_notna, Vigo_phone_notna, HVN_nophone, HVN_phone_na, Vigo_nophone, Vigo_phone_na):
    teleco1['Đầu Số Cũ'] = '0' + teleco1['Đầu Số Cũ'].astype(str)
    teleco1['Đầu Số Mới'] = '0' + teleco1['Đầu Số Mới'].astype(str)

    teleco2['Mã vùng điện thoại cũ\t'] = '0' + teleco2['Mã vùng điện thoại cũ\t'].astype(str)
    teleco2['Mã vùng điện thoại mới\t'] = '0' + teleco2['Mã vùng điện thoại mới\t'].astype(str)

    HVN_dausomoi, HVN_nodausomoi= check_dausomoi(HVN_phone_notna, teleco1)
    HVN_mavungmoi, HVN_nomavungmoi= check_mavungmoi(HVN_nodausomoi, teleco2)

    Vigo_dausomoi, Vigo_nodausomoi= check_dausomoi(Vigo_phone_notna, teleco1)
    Vigo_mavungmoi, Vigo_nomavungmoi= check_mavungmoi(Vigo_nodausomoi, teleco2)

    HVN_khongthoa = pd.concat([HVN_nophone, HVN_phone_na])
    HVN_khongthoa = pd.concat([HVN_khongthoa, HVN_nomavungmoi])

    Vigo_khongthoa = pd.concat([Vigo_nophone, Vigo_phone_na])
    Vigo_khongthoa = pd.concat([Vigo_khongthoa, Vigo_nomavungmoi])

    HVN_thoa = pd.concat([HVN_dausomoi, HVN_mavungmoi])
    Vigo_thoa = pd.concat([Vigo_dausomoi, Vigo_mavungmoi])

    return HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa

def calculate_distance_round1(lat1, lon1, lat2, lon2):
    return geodesic((lat1, lon1), (lat2, lon2)).meters

def round1(HVN_thoa, Vigo_thoa, threshold):
    if len(HVN_thoa['Phone'].unique()) < len(Vigo_thoa['Phone'].unique()):
        phone_list = HVN_thoa['Phone'].unique().tolist() 
    else:
        phone_list = Vigo_thoa['Phone'].unique().tolist()
    
    phonenum_map = pd.DataFrame()
    for phone_num in tqdm(phone_list):
        Data_df_phone = HVN_thoa[HVN_thoa['Phone'] == phone_num]
        VIGO_df_phone = Vigo_thoa[Vigo_thoa['Phone'] == phone_num]
        
        Data_df_phone['key'] = 1
        VIGO_df_phone['key'] = 1
        df_merged_by_phone = pd.merge(Data_df_phone, VIGO_df_phone, on='key', suffixes=('_file1', '_file2'))
        del df_merged_by_phone['key']
        phonenum_map = pd.concat([phonenum_map, df_merged_by_phone])

    if phonenum_map.empty:
        phonedistance_threshold = phonenum_map
    else:          
        # Tính khoảng cách
        phonenum_map['distance'] = phonenum_map.apply(lambda row: calculate_distance_round1(row['Latitude_file1'], row['Longitude_file1'],
                                                                                            row['Latitude_file2'], row['Longitude_file2']), axis=1) 
        phonedistance_threshold = phonenum_map[phonenum_map['distance'] <= threshold]
    
    return phonedistance_threshold

def tao_danh_sach_thoa_khongthoa_motfile(teleco1, teleco2, HVN_phone_notna, HVN_nophone, HVN_phone_na):
    teleco1['Đầu Số Cũ'] = '0' + teleco1['Đầu Số Cũ'].astype(str)
    teleco1['Đầu Số Mới'] = '0' + teleco1['Đầu Số Mới'].astype(str)

    teleco2['Mã vùng điện thoại cũ\t'] = '0' + teleco2['Mã vùng điện thoại cũ\t'].astype(str)
    teleco2['Mã vùng điện thoại mới\t'] = '0' + teleco2['Mã vùng điện thoại mới\t'].astype(str)

    HVN_dausomoi, HVN_nodausomoi= check_dausomoi(HVN_phone_notna, teleco1)
    HVN_mavungmoi, HVN_nomavungmoi= check_mavungmoi(HVN_nodausomoi, teleco2)

    HVN_khongthoa = pd.concat([HVN_nophone, HVN_phone_na])
    HVN_khongthoa = pd.concat([HVN_khongthoa, HVN_nomavungmoi])
    HVN_thoa = pd.concat([HVN_dausomoi, HVN_mavungmoi])

    return HVN_thoa, HVN_khongthoa

def round1_motfile(df, threshold):
    result = pd.merge(df, df, on=['Phone'],
                      how='inner', suffixes=('_1', '_2'))

    result_df = result[(result['OutletID_1'] != result['OutletID_2']) & (result['OutletID_1'] < result['OutletID_2'])]
    
    if result_df.empty:
        phonedistance_threshold = result_df
    else:
        # Tính khoảng cách
        result_df['distance'] = result_df.apply(lambda row: calculate_distance_round1(row['Latitude_1'], row['Longitude_1'],
                                                                                        row['Latitude_2'], row['Longitude_2']), axis=1) 
        phonedistance_threshold = result_df[result_df['distance'] <= threshold]
    
    return phonedistance_threshold

def is_valid_format(address):
    parts = address.split(', ')
    if len(parts) == 2:
        first_part = parts[0].split(' ')
        if len(first_part) >= 2 and first_part[1] == 'ấp' and 'thị trấn' in parts[1]:
            return True
    return False

def is_valid_format_1(address):
    if pd.isna(address):
        return False
    pattern = re.compile(r'\b\d+[a-zA-Z]*\s*ấp[^\d,]+\b')
    match = pattern.match(address)
    return bool(match and match.group(0) == address)

def is_valid_format_2(address):
    if pd.isna(address):
        return False
    pattern = re.compile(r'\b\d+\s*kênh xáng,\s*ấp (\d+),\s*xã (\D+)')
    match = pattern.match(address)
    return bool(match and match.group(1) and match.group(2))

def is_valid_format_3(address):
    if pd.isna(address):
        return False
    pattern = re.compile(r'\b30 cầu đường bàng,\s*xã (\D+)')
    match = pattern.match(address)
    return bool(match and match.group(1))

def is_valid_format_4(address):
    if pd.isna(address):
        return False
    pattern = re.compile(r'\b29 thuận hòa')
    return bool(re.match(pattern, address))

def is_valid_format_5(address):
    if pd.isna(address):
        return False
    pattern = re.compile(r'\b(\d+\s*hòa lạc c)\s*,\s*Xã (\D+)')
    return bool(re.match(pattern, address))

def is_valid_format_6(address):
    if pd.isna(address):
        return False
    pattern = re.compile(r'\b(\d+\s*cây khô lớn)\s*,\s*xã (\D+)')
    return bool(re.match(pattern, address))

def loc_hvn_r2(HVN_r2):
    HVN_r2['WardName'].fillna('', inplace=True)
    HVN_r2['WardName'].replace({None: ''}, inplace=True)
    HVN_r2['WardName'].replace({'NULL': ''}, inplace=True)
    HVN_r2['CustomerAddress'].fillna('', inplace=True)
    HVN_r2['CustomerAddress'].replace({None: ''}, inplace=True)
    HVN_r2['CustomerAddress'].replace({'NULL': ''}, inplace=True)
    HVN_r2['CustomerAddress'] = HVN_r2['CustomerAddress'].str.strip()
    HVN_r2['DistrictName'].fillna('', inplace=True)
    HVN_r2['DistrictName'].replace({None: ''}, inplace=True)
    HVN_r2['DistrictName'].replace({'NULL': ''}, inplace=True)
    HVN_r2['OutletName'].fillna('NoName', inplace=True)
    HVN_r2['OutletName'].replace({None: 'NoName'}, inplace=True)
    HVN_r2['OutletName'].replace({'NULL': 'NoName'}, inplace=True)
    HVN_r2['CustomerAddress'].fillna('', inplace=True)
    HVN_r2['CustomerAddress'].replace({None: ''}, inplace=True)
    HVN_r2['CustomerAddress'].replace({'NULL': ''}, inplace=True)
    HVN_r2['CustomerAddress'] = HVN_r2['CustomerAddress'].str.strip()
    HVN_r2['CustomerAddress'] = HVN_r2['CustomerAddress'].str.lower()

    HVN_digit_mask = HVN_r2[HVN_r2['CustomerAddress'].str.match(r'^\d')]
    HVN_notdigit_mask = HVN_r2[~HVN_r2['CustomerAddress'].str.match(r'^\d')]

    word_list = [
        'đường', ' đường', ' hương lộ', 'đ\\.', 'd\\.', 'bình thành','ngô y linh','an dương vương','phạm đăng giãng','phạm bành', 'đinh nghị xuân','đỗ năng tế','bùi hữu diện', 'đinh nghị xuân', 'đỗ năng tế', 'tây lân', 'bùi tư toàn','hoàng văn hợp', 'tỉnh lô', 'nguyễn triệu luật',  'nguyễn quý yêm', 'đỗ năng tế', 'trần đại nghĩa',  'bùi tư toàn', 'phùng tá chu', 'khiếu năng tĩnh', 'phan anh', 'nguyễn cửu phú', 'nguyễn quý yêm', 'trương thước phan', 'nguyễn thị tú', 'bình thành', 'bình long', 'hồ ngọc lãm', 'lê cơ', 'nguyễn thức tự','nguyễn văn cự', 'đình nghi xuân','lê tấn bê', 'lê trọng tấn','tân kỳ tân quý','kênh nước đen','số 4','827', 'kinh dương vương','trần văn giàu', 'bùi dương lịch', 'gò xoài', 'số 8b','số 1a','lê văn quới','lê đình cẩn', 'hồ học lãm', 'lô tư', 'bình trị đông', 'hồ văn long','liên khu', 'trần đại nghĩa', 'hồ văn long','phạm đăng giảng','miếu gò xoài','miếu gò xoài', '26/3', '26 tháng 3','liên khu 5 6', 'liên khu 5-6','ao đôi', 'miếu bình đông','trần thanh mại','trần thành đại', 'n27', 'nguyễn văn nhân','huỳnh văn thanh', 'võ văn thành', 'nguyễn hoà luông', 'mai thị non', 'lương văn bang', 'truong binh - phuoc lâm', 'lộ 837', 'huỳnh thị mai', 'đường 836','tiên đông thượng', 'lộ tránh', 'công lý', 'ban cao', 'caovăn lầu', 'bạch đằng', 'lộ thầy cai', 'bình an', 'nguyễn công truc', 'long khốt', 'duong', 'duong', 'bà chánh thâu','trần ngọc giải', 'dương văn dương', 'đ12', 'lê văn sáu', 'nguyễn văn tư', 'lê văn tám', 'đt', 'nguyễn đình chiểu', 'trương văn kỉnh', 'tiền phong', 'tô thị huỳnh', 'đặng ngọc sương', 'phan đình phùng', 'lê văn khuyên', 'nguyễn văn tiếp', 'nguyễn văn cương', 'lê văn tường', 'võ văn môn', 'lê lợi', 'nguyễn trãi', 'hùng vương', 'nguyễn thị nhỏ', 'nguyễn thị bảy', 'nguyễn chí thanh', 'thống chế sỹ', 'phạm văn thành', 'huynh chau so', 'huỳnh châu sổ', 'nguyễn đình chiểu', 'đỗ tường phong', 'sơn thông', 'đỗ trình thoại', 'nguyễn thông', 'lãnh binh thái', 'phạm văn thành', 'trần công oanh', 'đồng khởi', 'châu thị kim', 'lê văn tưởng', 'phạm ngũ lão', 'nguyễn văn trổi', 'nguyễn thái bình', 'hoàng hoa thám', 'đặng văn truyện', 'huỳnh văn đảnh', 'nguyễnvăn trưng', 'vành đai', 'nguyen thong', 'phú hoà', 'phan đình phùng', 'hoà hảo', 'tiền phong', 'nguyễn thông', 'nguyen trung truc', 'trương định', 'nguyễn thị định', 'nguyễn văn nhâm', 'ql', 'ql', 'ba sa gò mối', 'mỹ thuận', 'bùi hữu nghĩa', 'châu thị kim', 'cử luyện', 'nguyễn huệ', 'hoàng hoa thám', 'nguyễn văn tư', 'nguyễn huệ', 'đoàn hoàng minh', 'phan văn mảng', 'đồng khởi', 'nguyễn văn tuôi', 'tán kế', 'luu van te', 'châu thị kim', 'trần văn đấu', 'quách văn tuấn', 'sương nguyệt ánh', 'châu văn bảy', 'nguyễn trung trực', 'nguyễn văn cánh', 'nguyễn minh đường', 'nguyễn thị hạnh', 'đỗ đình thoại', 'nguyễn du', 'châu thị kim', 'trương vĩnh ký', 'nguyen thi dinh', 'hồ văn huê', 'nguyễn đáng', 'vĩnh phú', 'châu thị kim', 'đoàn hoàng minh', 'huỳnh việt thanh', 'nguyễn hữu thọ', 'luong van chan', 'phan đình phùng', 'phạm văn ngô', 'nguyen thong', 'đương 30/4', 'cmt8', 'cmt8', 'huỳnh tấn phát', 'hương lộ', 'hl', 'trần văn đạt', 'quốc lộ', 'tỉnh lộ', 'dt', 'dt', 'nguyễn an ninh', 'lê hồng phong', 'lộc trung', 'lê minh xuân', 'mai thị tốt', 'phạm văn ngô', 'tl', 'lê thị trâm', 'quoc lo', 'tỉnh lộ', 'nguyễn thị minh khai', 'phạm văn chiên', 'võ văn nhơn', 'lê hữu nghĩa', 'phan văn lay', 'châu văn giác', 'nguyễn huỳnh đức', 'phan văn mãng', 'bùi tấn', 'lưu nghiệp anh', 'lê hồng phong', 'nguyễn văn siêu', 'nguyễn văn quá', 'vo cong ton', 'thái hữu kiểm', 'trần minh châu', 'lý thường kiệt', 'phạm văn ngũ', 'trần phong sắc', 'nguyễn văn kỉnh', '827d', 'phan văn mãng', 'nguyễn cửu vân', 'bùi thị hồng', 'trần thế sinh', 'hoàng anh', 'huỳnh văn tạo', 'nguyễn văn trung', 'đỗ tường tự', 'nguyễn văn trưng', 'tl', 'đt', 'trần phú', 'nguyễn thị diện', '19/5', 'hl', 'nguyễn văn tiến', 'phan van lay', 'nguyen thi minh khai', 'đỗ tường tự', 'thủ khoa huân', 'thanh hà', 'tân long', 'truong bình', 'huỳnh thị lung', ' phan thanh giảng', ' phan thanh giảnp', 'đinh viết cừu', 'võ nguyên giáp', 'lộ dừa', 'truong vinh ky', 'phan văn tình', 'trịnh quang nghị', 'nguyễn minh trung', 'ca văn thỉnh', 'bàu sen', 'chu văn an', 'trần thị non', 'lê lợi', 'võ công tồn', 'nguyễntrung trực', 'phan van mang', 'phan văn mảng', 'phan văn mãng', 'nguyễn hòa luông', 'nguyễn văn trỗi', 'võ văn kiệt', 'huỳnh văn gấm', 'thanh hà', 'hòa lạc c', 'phạm văn ngô', 'phạm văn ngô', 'phước toàn', 'vỏ duy tạo', 'lảnh binh thái', 'nguyen cuu van', 'trần phú', 'cao văn lầu', 'điện biên phủ', 'bạch đằng' 'huỳnh văn thanh', 'võ văn tần', 'phan văn tình', 'chu van an', 'thuận hòa', 'vũ đình liệu', 'đồng văn dẫn', 'mậu thân', 'cao thị mai', 'nguyễn văn rành', 'nguyễn công trung', 'nguyễn minh trường', 'nguyễn quang đại', 'hai bà trưng', 'võ thị sáu', 'trần quốc tuấn', 'lê văn kiệt', 'nguyễn văn tạo', '30 tháng 4', '3/2', 'phan đình phùng', 'thủ khoa huân', 'phan văn tình', 'hoàng lam', 'ngô quyền', 'nguyễn thị bẹ', 'phan văn đạt', 'nguyễn minh trường', 'võ công tồn', 'huỳnh văn gấm', 'huỳnh văn lộng', 'bình hòa', 'nguyen huu tho', 'nguyễn hữu thọ', 'võ công tồn', 'trần phong sắc', 'trần phong sẳ', 'phạm ngọc tòng', 'phan văn tình', 'trần hưng đạo', 'nguyễn văn rành', 'nguyễn văn cảnh', 'thủ khoa thừa', 'lê thị điền', 'rạch tre', 'trần hưng dạo', 'võ công tồn', 'võ hồng cúc', 'lê văn kiệt', 'phạm văn trạch', 'lê văn tao', 'nguyễn thiện thành', 'huỳnh hữu thống', '2 tháng 9', 'phan châu trinh', 'hoàng lam', 'trần văn trà', 'nguyễn thị út', 'nguyễn thị út', 'bình trị 2', 'lê văn trần', 'trưng nhị', 'bình hòa', 'nguyễn đìnhchiểu', 'hương lộ', 'nguyen thi bay', 'nguyễn thị bảy', 'đt 816', 'huỳnh văn đảnh', 'huỳnh văn đảnh', 'nguyễn văn tiếp', 'nguyễn văn tiếp', 'cao thi mai', 'đt825', 'đặng văn búp', '30 thang 4', 'nguyễn bỉnh khiêm', 'đt 835b'
    ]

    pattern = '|'.join(word_list)

    df_filtered = HVN_digit_mask[HVN_digit_mask['CustomerAddress'].str.contains(pattern, regex=True)]
    df_notfiltered = HVN_digit_mask[~HVN_digit_mask['CustomerAddress'].str.contains(pattern, regex=True)]

    regex_pattern = r'\b\d+ ấp [^\d]+, xã \w+\b'

    ap_ten = df_filtered[df_filtered['CustomerAddress'].str.contains(regex_pattern, regex=True, case=False)]
    non_ap_ten = df_filtered.loc[~df_filtered['CustomerAddress'].str.contains(regex_pattern, regex=True, case=False)]
    so_ap = non_ap_ten[non_ap_ten['CustomerAddress'].str.match(r'^\d+ ấp [^qlhlđthldlt]+\b(?:(?!ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ|đinh viết cừu|nguyễn thông).)*$')]
    noso_ap = non_ap_ten[~non_ap_ten['CustomerAddress'].str.match(r'^\d+ ấp [^qlhlđthldlt]+\b(?:(?!ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ|đinh viết cừu|nguyễn thông).)*$')]
    ap = noso_ap[noso_ap['CustomerAddress'].str.match(r'^\d+ ấp (?!.*\b(ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ)\b)[^\d]+(\s+\d+)?$')]
    no_ap = noso_ap[~noso_ap['CustomerAddress'].str.match(r'^\d+ ấp (?!.*\b(ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ)\b)[^\d]+(\s+\d+)?$')]
    xa = no_ap[noso_ap['CustomerAddress'].str.match(r'^\d+ xã (?!.*\b(ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ)\b)[^\d]+(\s+\d+)?$')]
    no_xa = no_ap[~no_ap['CustomerAddress'].str.match(r'^\d+ xã (?!.*\b(ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ)\b)[^\d]+(\s+\d+)?$')]
    ap2 = no_xa[no_xa['CustomerAddress'].str.match(r'\d+/[^ ]+ ấp [^,]+')]
    no_ap2 = no_xa[~no_xa['CustomerAddress'].str.match(r'\d+/[^ ]+ ấp [^,]+')]
    xa2 = no_ap2[no_ap2['CustomerAddress'].str.match(r'\d+/[^ ]+ xã [^,]+')]
    no_xa2 = no_ap2[~no_ap2['CustomerAddress'].str.match(r'\d+/[^ ]+ xã [^,]+')]
    ap_thitran = no_xa2[no_xa2['CustomerAddress'].apply(is_valid_format)]
    noap_thitran = no_xa2[~no_xa2['CustomerAddress'].apply(is_valid_format)]
    ap_df = noap_thitran[noap_thitran['CustomerAddress'].apply(lambda x: is_valid_format_1(x) if not pd.isna(x) else False)]
    no_ap_df = noap_thitran[~noap_thitran['CustomerAddress'].apply(lambda x: is_valid_format_1(x) if not pd.isna(x) else False)]
    ap_df_2 = no_ap_df[no_ap_df['CustomerAddress'].str.match(r'^\d+ ap [^qlhlđthldlt]+\b(?:(?!ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ|đinh viết cừu|nguyễn thông).)*$')]
    no_ap_df_2 = no_ap_df[~no_ap_df['CustomerAddress'].str.match(r'^\d+ ap [^qlhlđthldlt]+\b(?:(?!ql|hl|đt|hương lộ|ql|tl|tl|dt|quốc lộ|tỉnh lộ|đinh viết cừu|nguyễn thông).)*$')]
    kenhxang = no_ap_df_2[no_ap_df_2['CustomerAddress'].apply(lambda x: is_valid_format_2(x) if not pd.isna(x) else False)]
    no_kenhxang = no_ap_df_2[~no_ap_df_2['CustomerAddress'].apply(lambda x: is_valid_format_2(x) if not pd.isna(x) else False)]
    cauduongbang = no_kenhxang[no_kenhxang['CustomerAddress'].apply(lambda x: is_valid_format_3(x) if not pd.isna(x) else False)]
    no_cauduongbang = no_kenhxang[~no_kenhxang['CustomerAddress'].apply(lambda x: is_valid_format_3(x) if not pd.isna(x) else False)]
    thuanhoa = no_cauduongbang[no_cauduongbang['CustomerAddress'].apply(lambda x: is_valid_format_4(x) if not pd.isna(x) else False)]
    no_thuanhoa = no_cauduongbang[~no_cauduongbang['CustomerAddress'].apply(lambda x: is_valid_format_4(x) if not pd.isna(x) else False)]
    hoa_lac_c = no_thuanhoa[no_thuanhoa['CustomerAddress'].apply(lambda x: is_valid_format_5(x) if not pd.isna(x) else False)]
    no_hoa_lac_c = no_thuanhoa[~no_thuanhoa['CustomerAddress'].apply(lambda x: is_valid_format_5(x) if not pd.isna(x) else False)]
    
    pattern = re.compile(r'\b695/4 bình trị 2, xã thuận mỹ\b')

    binhtri = no_hoa_lac_c[no_hoa_lac_c['CustomerAddress'].str.contains(pattern, na=False, regex=True)]
    no_binhtri = no_hoa_lac_c[~no_hoa_lac_c['CustomerAddress'].str.contains(pattern, na=False, regex=True)]
    caykho = no_binhtri[no_binhtri['CustomerAddress'].apply(lambda x: is_valid_format_6(x) if not pd.isna(x) else False)]
    no_caykho = no_binhtri[~no_binhtri['CustomerAddress'].apply(lambda x: is_valid_format_6(x) if not pd.isna(x) else False)]

    pattern = re.compile(r'\b(bình an)\s*,\s*xã (\S+)\b')

    binhan = no_caykho[no_caykho['CustomerAddress'].str.contains(pattern, na=False, regex=True)]
    no_binhan = no_caykho[~no_caykho['CustomerAddress'].str.contains(pattern, na=False, regex=True)]

    df_khongthoa = pd.concat([HVN_notdigit_mask, df_notfiltered])
    df_khongthoa = pd.concat([df_khongthoa, ap_ten])
    df_khongthoa = pd.concat([df_khongthoa, so_ap])
    df_khongthoa = pd.concat([df_khongthoa, ap])
    df_khongthoa = pd.concat([df_khongthoa, xa])
    df_khongthoa = pd.concat([df_khongthoa, ap2])
    df_khongthoa = pd.concat([df_khongthoa, xa2])
    df_khongthoa = pd.concat([df_khongthoa, ap_thitran])
    df_khongthoa = pd.concat([df_khongthoa, ap_df])
    df_khongthoa = pd.concat([df_khongthoa, ap_df_2])
    df_khongthoa = pd.concat([df_khongthoa, kenhxang])
    df_khongthoa = pd.concat([df_khongthoa, cauduongbang])
    df_khongthoa = pd.concat([df_khongthoa, thuanhoa])
    df_khongthoa = pd.concat([df_khongthoa, hoa_lac_c])
    df_khongthoa = pd.concat([df_khongthoa, binhtri])
    df_khongthoa = pd.concat([df_khongthoa, caykho])
    df_khongthoa = pd.concat([df_khongthoa, binhan])

    pattern = re.compile(r'\b19 nguyễn văn nhân, xã thanh phú\b')

    nguyennhan = df_khongthoa[df_khongthoa['CustomerAddress'].str.contains(pattern, na=False, regex=True)]
    no_nguyennhan = df_khongthoa[~df_khongthoa['CustomerAddress'].str.contains(pattern, na=False, regex=True)]

    word_list = [
        'đường', ' đường', ' hương lộ', 'đ\\.', 'd\\.', 'bình thành', 'phạm bành', 'ngô y linh','an dương vương','phạm đăng giãng', 'đinh nghị xuân','đỗ năng tế','bùi hữu diện', 'đinh nghị xuân', 'đỗ năng tế', 'tây lân', 'bùi tư toàn','hoàng văn hợp', 'tỉnh lô', 'nguyễn triệu luật',  'nguyễn quý yêm', 'đỗ năng tế', 'trần đại nghĩa',  'bùi tư toàn', 'phùng tá chu', 'khiếu năng tĩnh', 'phan anh', 'nguyễn cửu phú', 'nguyễn quý yêm', 'trương thước phan', 'nguyễn thị tú', 'bình thành', 'bình long', 'hồ ngọc lãm', 'lê cơ', 'nguyễn thức tự','nguyễn văn cự', 'đình nghi xuân','lê tấn bê', 'lê trọng tấn','tân kỳ tân quý','kênh nước đen','số 4','827', 'kinh dương vương','trần văn giàu', 'bùi dương lịch', 'gò xoài', 'số 8b','số 1a','lê văn quới','lê đình cẩn', 'hồ học lãm', 'lô tư', 'bình trị đông', 'hồ văn long','liên khu', 'trần đại nghĩa', 'hồ văn long','phạm đăng giảng','miếu gò xoài','miếu gò xoài', '26/3', '26 tháng 3','liên khu 5 6', 'liên khu 5-6','ao đôi', 'miếu bình đông','trần thanh mại','trần thành đại', 'n27', 'nguyễn văn nhân','huỳnh văn thanh', 'võ văn thành', 'nguyễn hoà luông', 'mai thị non', 'lương văn bang', 'truong binh - phuoc lâm', 'lộ 837', 'huỳnh thị mai', 'đường 836','tiên đông thượng', 'lộ tránh', 'công lý', 'ban cao', 'caovăn lầu', 'bạch đằng', 'lộ thầy cai', 'bình an', 'nguyễn công truc', 'long khốt', 'duong', 'duong', 'bà chánh thâu','trần ngọc giải', 'dương văn dương', 'đ12', 'lê văn sáu', 'nguyễn văn tư', 'lê văn tám', 'đt', 'nguyễn đình chiểu', 'trương văn kỉnh', 'tiền phong', 'tô thị huỳnh', 'đặng ngọc sương', 'phan đình phùng', 'lê văn khuyên', 'nguyễn văn tiếp', 'nguyễn văn cương', 'lê văn tường', 'võ văn môn', 'lê lợi', 'nguyễn trãi', 'hùng vương', 'nguyễn thị nhỏ', 'nguyễn thị bảy', 'nguyễn chí thanh', 'thống chế sỹ', 'phạm văn thành', 'huynh chau so', 'huỳnh châu sổ', 'nguyễn đình chiểu', 'đỗ tường phong', 'sơn thông', 'đỗ trình thoại', 'nguyễn thông', 'lãnh binh thái', 'phạm văn thành', 'trần công oanh', 'đồng khởi', 'châu thị kim', 'lê văn tưởng', 'phạm ngũ lão', 'nguyễn văn trổi', 'nguyễn thái bình', 'hoàng hoa thám', 'đặng văn truyện', 'huỳnh văn đảnh', 'nguyễnvăn trưng', 'vành đai', 'nguyen thong', 'phú hoà', 'phan đình phùng', 'hoà hảo', 'tiền phong', 'nguyễn thông', 'nguyen trung truc', 'trương định', 'nguyễn thị định', 'nguyễn văn nhâm', 'ql', 'ql', 'ba sa gò mối', 'mỹ thuận', 'bùi hữu nghĩa', 'châu thị kim', 'cử luyện', 'nguyễn huệ', 'hoàng hoa thám', 'nguyễn văn tư', 'nguyễn huệ', 'đoàn hoàng minh', 'phan văn mảng', 'đồng khởi', 'nguyễn văn tuôi', 'tán kế', 'luu van te', 'châu thị kim', 'trần văn đấu', 'quách văn tuấn', 'sương nguyệt ánh', 'châu văn bảy', 'nguyễn trung trực', 'nguyễn văn cánh', 'nguyễn minh đường', 'nguyễn thị hạnh', 'đỗ đình thoại', 'nguyễn du', 'châu thị kim', 'trương vĩnh ký', 'nguyen thi dinh', 'hồ văn huê', 'nguyễn đáng', 'vĩnh phú', 'châu thị kim', 'đoàn hoàng minh', 'huỳnh việt thanh', 'nguyễn hữu thọ', 'luong van chan', 'phan đình phùng', 'phạm văn ngô', 'nguyen thong', 'đương 30/4', 'cmt8', 'cmt8', 'huỳnh tấn phát', 'hương lộ', 'hl', 'trần văn đạt', 'quốc lộ', 'tỉnh lộ', 'dt', 'dt', 'nguyễn an ninh', 'lê hồng phong', 'lộc trung', 'lê minh xuân', 'mai thị tốt', 'phạm văn ngô', 'tl', 'lê thị trâm', 'quoc lo', 'tỉnh lộ', 'nguyễn thị minh khai', 'phạm văn chiên', 'võ văn nhơn', 'lê hữu nghĩa', 'phan văn lay', 'châu văn giác', 'nguyễn huỳnh đức', 'phan văn mãng', 'bùi tấn', 'lưu nghiệp anh', 'lê hồng phong', 'nguyễn văn siêu', 'nguyễn văn quá', 'vo cong ton', 'thái hữu kiểm', 'trần minh châu', 'lý thường kiệt', 'phạm văn ngũ', 'trần phong sắc', 'nguyễn văn kỉnh', '827d', 'phan văn mãng', 'nguyễn cửu vân', 'bùi thị hồng', 'trần thế sinh', 'hoàng anh', 'huỳnh văn tạo', 'nguyễn văn trung', 'đỗ tường tự', 'nguyễn văn trưng', 'tl', 'đt', 'trần phú', 'nguyễn thị diện', '19/5', 'hl', 'nguyễn văn tiến', 'phan van lay', 'nguyen thi minh khai', 'đỗ tường tự', 'thủ khoa huân', 'thanh hà', 'tân long', 'truong bình', 'huỳnh thị lung', ' phan thanh giảng', ' phan thanh giảnp', 'đinh viết cừu', 'võ nguyên giáp', 'lộ dừa', 'truong vinh ky', 'phan văn tình', 'trịnh quang nghị', 'nguyễn minh trung', 'ca văn thỉnh', 'bàu sen', 'chu văn an', 'trần thị non', 'lê lợi', 'võ công tồn', 'nguyễntrung trực', 'phan van mang', 'phan văn mảng', 'phan văn mãng', 'nguyễn hòa luông', 'nguyễn văn trỗi', 'võ văn kiệt', 'huỳnh văn gấm', 'thanh hà', 'hòa lạc c', 'phạm văn ngô', 'phạm văn ngô', 'phước toàn', 'vỏ duy tạo', 'lảnh binh thái', 'nguyen cuu van', 'trần phú', 'cao văn lầu', 'điện biên phủ', 'bạch đằng' 'huỳnh văn thanh', 'võ văn tần', 'phan văn tình', 'chu van an', 'thuận hòa', 'vũ đình liệu', 'đồng văn dẫn', 'mậu thân', 'cao thị mai', 'nguyễn văn rành', 'nguyễn công trung', 'nguyễn minh trường', 'nguyễn quang đại', 'hai bà trưng', 'võ thị sáu', 'trần quốc tuấn', 'lê văn kiệt', 'nguyễn văn tạo', '30 tháng 4', '3/2', 'phan đình phùng', 'thủ khoa huân', 'phan văn tình', 'hoàng lam', 'ngô quyền', 'nguyễn thị bẹ', 'phan văn đạt', 'nguyễn minh trường', 'võ công tồn', 'huỳnh văn gấm', 'huỳnh văn lộng', 'bình hòa', 'nguyen huu tho', 'nguyễn hữu thọ', 'võ công tồn', 'trần phong sắc', 'trần phong sẳ', 'phạm ngọc tòng', 'phan văn tình', 'trần hưng đạo', 'nguyễn văn rành', 'nguyễn văn cảnh', 'thủ khoa thừa', 'lê thị điền', 'rạch tre', 'trần hưng dạo', 'võ công tồn', 'võ hồng cúc', 'lê văn kiệt', 'phạm văn trạch', 'lê văn tao', 'nguyễn thiện thành', 'huỳnh hữu thống', '2 tháng 9', 'phan châu trinh', 'hoàng lam', 'trần văn trà', 'nguyễn thị út', 'nguyễn thị út', 'bình trị 2', 'lê văn trần', 'trưng nhị', 'bình hòa', 'nguyễn đìnhchiểu', 'hương lộ', 'nguyen thi bay', 'nguyễn thị bảy', 'đt 816', 'huỳnh văn đảnh', 'huỳnh văn đảnh', 'nguyễn văn tiếp', 'nguyễn văn tiếp', 'cao thi mai', 'đt825', 'đặng văn búp', '30 thang 4', 'nguyễn bỉnh khiêm', 'đt 835b'
    ]

    pattern = '|'.join(word_list)
    df_filtered_2 = no_nguyennhan[no_nguyennhan['CustomerAddress'].str.contains(pattern, regex=True)]
    df_notfiltered_2 = no_nguyennhan[~no_nguyennhan['CustomerAddress'].str.contains(pattern, regex=True)]
    df_thoa = pd.concat([no_binhan, nguyennhan])
    df_thoa = pd.concat([df_thoa, df_filtered_2])
    
    return df_thoa, df_notfiltered_2

def xuly_toadotrongaddress_vigo(Vigo_r2):
    contains_plus = Vigo_r2[Vigo_r2['CustomerAddress'].str.contains('\\+')]
    not_contains_plus = Vigo_r2[~Vigo_r2['CustomerAddress'].str.contains('\\+')]

    contains_plus['plus_word'] = contains_plus['CustomerAddress'].str.extractall(r'(\S+\+\S+)').groupby(level=0).agg(','.join)[0]

    # Check for NaN values before applying the replacement
    contains_plus['CustomerAddress'] = contains_plus.apply(lambda row: row['CustomerAddress'].replace(row['plus_word'], '') if pd.notna(row['plus_word']) else row['CustomerAddress'], axis=1)

    contains_plus = contains_plus.drop('plus_word', axis=1)    

    vigo = pd.concat([contains_plus, not_contains_plus])

    return vigo

def convert_district(match):
    district_number = match.group(1)
    return f'phường {district_number}'

def has_street_name(address):
    street_name_pattern = r'\b(?:\w+\s*)?(\d+(?:\/\d+)?\s*[abcd]?[^\d]*\s*\d*(?:\s*\d+(?:\/\d+)?)?\s*[abcd]?[^\d]*(?:phạm đăng giãng|ngô y linh|bình thành|phạm bành|đinh nghị xuân|an dương vương|đỗ năng tế|bùi hữu diện|đinh nghị xuân|đỗ năng tế|tây lân|bùi tư toàn|tây lân|hoàng văn hợp|tỉnh lô|nguyễn triệu luật|nguyễn quý yêm|đỗ năng tế|trần đại nghĩa|bùi tư toàn|phùng tá chu|khiếu năng tĩnh|phan anh|nguyễn cửu phú|nguyễn quý yêm|trương thước phan|nguyễn thị tú|bình thành|đường|đường|đ\\.|d\\.|duong|duong|đại lộ đồng khởi|tân kỳ tân quý|hồ ngọc lãm|lê cơ|lê tấn bê|lê trọng tấn|bình long|nguyễn thức tự|đình nghi xuân|nguyễn văn cự|Kênh Nước Đen|kênh nước đen|kinh dương vương|số 4|bùi dương lịch|trần văn giàu|số 8b|gò xoài|số 1a|lê văn quới|hồ văn long|hồ học lãm|bình trị đông|hồ văn long|ao đôi|miếu bình đông|trần thanh mại|trần thành đại|26/3|26 tháng 3|liên khu|liên khu 5 6|liên khu 5-6|miếu gò xoài|phạm đăng giảng|lê đình cẩn|lộ phước hiệp|đương lộ làng|phan đình phùng|trương văn kỉnh|nguyễn đình chiểu|phú hoà|phan đình phùng|hoà hảo|tiền phong|lê văn tám|nguyễn bỉnh khiêm|tô thị huỳnh|lê văn khuyên|nguyễn văn tiếp|nguyễn văn cương|lê văn tường|võ văn môn|lê lợi|nguyễn trãi|hùng vương|nguyễn thị nhỏ|nguyễn thị bảy|nguyễn chí thanh|thống chế sỹ|phạm văn thành|huynh chau so|huỳnh châu sổ|nguyễn đình chiểu|đỗ tường phong|sơn thông|đỗ trình thoại|nguyễn thông|lãnh binh thái|phạm văn thành|trần công oanh|đồng khởi|châu thị kim|lê văn tưởng|phạm ngũ lão|nguyễn văn trổi|nguyễn thái bình|hoàng hoa thám|đặng văn truyện|huỳnh văn đảnh|nguyễnvăn trưng|vành đai|nguyen thong|nguyễn thông|nguyen trung truc|trương định|nguyễn thị định|nguyễn văn nhâm|ql|ql|ba sa gò mối|mỹ thuận|bùi hữu nghĩa|châu thị kim|cử luyện|nguyễn huệ|hoàng hoa thám|nguyễn văn tư|nguyễn huệ|đoàn hoàng minh|phan văn mảng|đồng khởi|nguyễn văn tuôi|tán kế|châu thị kim|trần văn đấu|sương nguyệt ánh|châu văn bảy|nguyễn trung trực|nguyễn văn cánh|nguyễn minh đường|nguyễn thị hạnh|đỗ đình thoại|nguyễn du|châu thị kim|trương vĩnh ký|nguyen thi dinh|hồ văn huê|nguyễn đáng|vĩnh phú|châu thị kim|đoàn hoàng minh|huỳnh việt thanh|nguyễn hữu thọ|luong van chan|phan đình phùng|phạm văn ngô|nguyen thong|đương 30/4|cmt8|cmt8|huỳnh tấn phát|hương lộ|hl|trần văn đạt|quốc lộ|hương lộ|tỉnh lộ|dt|dt|nguyễn an ninh|lê hồng phong|lộc trung|lê minh xuân|mai thị tốt|phạm văn ngô|tl|lê thị trâm|quoc lo|tỉnh lộ|nguyễn thị minh khai|phạm văn chiên|võ văn nhơn|lê hữu nghĩa|phan văn lay|châu văn giác|nguyễn huỳnh đức|phan văn mãng|bùi tấn|lưu nghiệp anh|lê hồng phong|nguyễn văn siêu|nguyễn văn quá|vo cong ton|thái hữu kiểm|trần minh châu|lý thường kiệt|phạm văn ngũ|trần phong sắc|nguyễn văn kỉnh|phan văn mãng|nguyễn cửu vân|bùi thị hồng|trần thế sinh|hoàng anh|huỳnh văn tạo|nguyễn văn trung|đỗ tường tự|nguyễn văn trưng|tl|đt|trần phú|nguyễn thị diện|nguyễn văn tiến|phan van lay|nguyen thi minh khai|đỗ tường tự|thủ khoa huân|thanh hà|tân long|truong bình|huỳnh thị lung| phan thanh giảng| phan thanh giảnp|đinh viết cừu|võ nguyên giáp|lộ dừa|truong vinh ky|phan văn tình|trịnh quang nghị|nguyễn minh trung|ca văn thỉnh|bàu sen|chu văn an|trần thị non|lê lợi|võ công tồn|nguyễntrung trực|phan van mang|phan văn mảng|phan văn mãng|nguyễn hòa luông|nguyễn văn trỗi|võ văn kiệt|huỳnh văn gấm|thanh hà|hòa lạc c|phạm văn ngô|phạm văn ngô|phước toàn|vỏ duy tạo|lảnh binh thái|nguyen cuu van|trần phú|cao văn lầu|điện biên phủ|bạch đằng|phú hòa|huỳnh văn thanh|võ văn tần|phan văn tình|chu van an|thuận hòa|vũ đình liệu|đồng văn dẫn|mậu thân|cao thị mai|nguyễn văn rành|nguyễn công trung|nguyễn minh trường|nguyễn quang đại|hai bà trưng|võ thị sáu|trần quốc tuấn|lê văn kiệt|nguyễn văn tạo|30 tháng 4|3/2|phan đình phùng|thủ khoa huân|phan văn tình|hoàng lam|ngô quyền|nguyễn thị bẹ|phan văn đạt|nguyễn minh trường|võ công tồn|huỳnh văn gấm|huỳnh văn lộng|bình hòa|nguyen huu tho|nguyễn hữu thọ|võ công tồn|trần phong sắc|trần phong sẳ|phạm ngọc tòng|phan văn tình|trần hưng đạo|nguyễn văn rành|nguyễn văn cảnh|thủ khoa thừa|lê thị điền|rạch tre|trần hưng dạo|võ công tồn|võ hồng cúc|lê văn kiệt|phạm văn trạch|lê văn tao|nguyễn thiện thành|huỳnh hữu thống|2 tháng 9|phan châu trinh|hoàng lam|trần văn trà|nguyễn thị út|nguyễn thị út|bình trị 2|lê văn trần|trưng nhị|bình hòa|nguyễn đìnhchiểu|hương lộ|nguyen thi bay|nguyễn thị bảy|đt 816|huỳnh văn đảnh|huỳnh văn đảnh|nguyễn văn tiếp|nguyễn văn tiếp|cao thi mai|đt825|đặng văn búp|30 thang 4|đt 835b)\s*\S*)\b'
    return bool(re.search(street_name_pattern, address))

def loc_vigo_r2(vigo_lower):
    columns_to_lowercase = ['CustomerAddress', 'WardName', 'DistrictName', 'ProvinceName']
    vigo_lower[columns_to_lowercase] = vigo_lower[columns_to_lowercase].apply(lambda x: x.astype(str))
    vigo_lower['CustomerAddress'] = vigo_lower['CustomerAddress'].apply(lambda x: ', '.join(dict.fromkeys(x.split(', '))))
    vigo_lower['CustomerAddress'] = vigo_lower['CustomerAddress'].apply(lambda x: re.sub(r'\bp(\d+)\b', convert_district, x))
    vigo_lower['CustomerAddress'] = vigo_lower['CustomerAddress'].apply(lambda x: ', '.join(dict.fromkeys(x.split(', '))))
    vigo_lower['CustomerAddress'] = vigo_lower['CustomerAddress'].str.lower()
    with_street_vigo_lower = vigo_lower[vigo_lower['CustomerAddress'].apply(has_street_name)]
    without_street_vigo_lower = vigo_lower[~vigo_lower['CustomerAddress'].apply(has_street_name)]
    contains_keywords = with_street_vigo_lower[with_street_vigo_lower['CustomerAddress'].str.contains('trụ điện|trụ|khóm|tru điện|tru dien|tđ|chợ|chợ|ngã 4|ngã 3|ấp an vĩnh|gần khánh uyên 1|cột điện|ấp 2|cột|hẻm|kp2|ấp 4|ấp mới 2|ấp bàu sen|ấp nô công|cộ|apa an vĩnh 1', case=False, regex=True)]
    does_not_contain_keywords = with_street_vigo_lower[ ~with_street_vigo_lower['CustomerAddress'].str.contains('trụ điện|trụ|khóm|tru điện|tru dien|tđ|chợ|chợ|ngã 4|ngã 3|ấp an vĩnh|gần khánh uyên 1|cột điện|ấp 2|cột|hẻm|kp2|ấp 4|ấp mới 2|ấp bàu sen|ấp nô công|cộ|apa an vĩnh 1', case=False, regex=True)]
    df_khongthoa = pd.concat([without_street_vigo_lower, contains_keywords])
    contains_keywords_2 = df_khongthoa[df_khongthoa['CustomerAddress'].str.contains('1404 đong trị|191, tỉnh lộ 914|24a tấn đức', case=False, regex=True)]
    does_not_contain_keywords_2 = df_khongthoa[ ~df_khongthoa['CustomerAddress'].str.contains('1404 đong trị|191, tỉnh lộ 914|24a tấn đức', case=False, regex=True)]
    df_thoa = does_not_contain_keywords.copy()
    df_thoa = pd.concat([df_thoa, contains_keywords_2])
    df_khongthoa = does_not_contain_keywords_2.copy()    
    df_khongthoa['CustomerAddress'] = df_khongthoa['CustomerAddress'].replace(to_replace=r'Unnamed', value='', regex=True)

    return df_thoa, df_khongthoa

def extract_location(text):
    match = re.search(r'(.+?(?:xã|phường|thị trấn)(?=\s|$))', text)
    if match:
        result = match.group(1)
    else:
        result = text
    return result.strip()
    
def xuly_address_hvn(OptionalText, data, text_remove):
    OptionalText['Replace'].fillna('', inplace=True)
    OptionalText['Replace'].replace({None: ''}, inplace=True)
    OptionalText['Replace'].replace({'NULL': ''}, inplace=True)

    for index, row in OptionalText.iterrows():
        optional_text = row['Optional']
        replace_text = row['Replace']
        
        data['CustomerAddress'] = data['CustomerAddress'].str.replace(optional_text, replace_text)

    data['result'] = data['CustomerAddress'].apply(extract_location)

    text_remove['Replace'].fillna('', inplace=True)
    text_remove['Replace'].replace({None: ''}, inplace=True)
    text_remove['Replace'].replace({'NULL': ''}, inplace=True)\

    # Vòng lặp qua từng hàng của OptionalText
    for index, row in text_remove.iterrows():
        optional_text = row['Text']
        replace_text = row['Replace']
        
        # Thực hiện thay thế trong cột 'Address' của HVN
        data['result'] = data['result'].str.replace(optional_text, replace_text)

    return data

def xuly_address_Vigo(OptionalText, data, text_remove):
    OptionalText['Replace'].fillna('', inplace=True)
    OptionalText['Replace'].replace({None: ''}, inplace=True)
    OptionalText['Replace'].replace({'NULL': ''}, inplace=True)

    data['result'] = data['CustomerAddress'].apply(extract_location)

    text_remove['Replace'].fillna('', inplace=True)
    text_remove['Replace'].replace({None: ''}, inplace=True)
    text_remove['Replace'].replace({'NULL': ''}, inplace=True)

    for index, row in text_remove.iterrows():
        optional_text = row['Text']
        replace_text = row['Replace']
        
        # Thực hiện thay thế trong cột 'Address' của HVN
        data['result'] = data['result'].str.replace(optional_text, replace_text)   
    
    return data

def tao_address(data):
    data['WardName'].fillna('', inplace=True)
    data['WardName'].replace({None: ''}, inplace=True)
    data['WardName'].replace({'NULL': ''}, inplace=True)

    data['DistrictName'].fillna('', inplace=True)
    data['DistrictName'].replace({None: ''}, inplace=True)
    data['DistrictName'].replace({'NULL': ''}, inplace=True)

    data['Address'] = data['result'] + data['WardName'] + data['DistrictName'] + data['ProvinceName']

    Op = pd.read_excel("Op_Text_vigo.xlsx")

    Op['Replace'].fillna('', inplace=True)
    Op['Replace'].replace({None: ''}, inplace=True)
    Op['Replace'].replace({'NULL': ''}, inplace=True)

    # Vòng lặp qua từng hàng của OptionalText
    for index, row in Op.iterrows():
        optional_text = row['Optional']
        replace_text = row['Replace']
        
        # Check if replace_text is a string
        if not isinstance(replace_text, str):
            # Convert replace_text to string or handle accordingly
            replace_text = str(replace_text)

        # Thực hiện thay thế trong cột 'Address' của HVN
        data['Address'] = data['Address'].str.replace(optional_text, replace_text)

    return data

def fuzzy_similarity(row):
    return fuzz.token_set_ratio(row['Address_file1'], row['Address_file2'])

def round2(data1, data2):
    data1['Address'] = data1['Address'].str.lower()
    data1['Address'] = data1['Address'].apply(lambda x: re.sub(r'[^a-z0-9\s/]', '', x))
    data1['Address'] = data1['Address'].apply(lambda x: re.sub(r'\s', '', x))
    data2['Address'] = data2['Address'].str.lower()
    data2['Address'] = data2['Address'].apply(lambda x: re.sub(r'[^a-z0-9\s/]', '', x))
    data2['Address'] = data2['Address'].apply(lambda x: re.sub(r'\s', '', x))
    data1['ProvinceName'] = data1['ProvinceName'].str.lower()
    data1['DistrictName'] = data1['DistrictName'].str.lower()
    data1['WardName'] = data1['WardName'].str.lower()
    data2['ProvinceName'] = data2['ProvinceName'].str.lower()
    data2['DistrictName'] = data2['DistrictName'].str.lower()
    data2['WardName'] = data2['WardName'].str.lower()

    result = pd.merge(data1, data2, left_on=['ProvinceName', 'DistrictName', 'WardName'],
                    right_on=['ProvinceName', 'DistrictName', 'WardName'], how='inner', suffixes=('_file1', '_file2'))

    result['fuzzy_similarity'] = result.apply(fuzzy_similarity, axis=1)
    matching_rows_fuzzy = result[result['fuzzy_similarity'] == 100]

    return matching_rows_fuzzy

def fuzzy_similarity_motfile(row):
    return fuzz.token_set_ratio(row['Address_1'], row['Address_2'])

def round2_motfile(data1):
    data1['Address'] = data1['Address'].str.lower()
    data1['Address'] = data1['Address'].apply(lambda x: re.sub(r'[^a-z0-9\s/]', '', x))
    data1['Address'] = data1['Address'].apply(lambda x: re.sub(r'\s', '', x))
    data1['ProvinceName'] = data1['ProvinceName'].str.lower()
    data1['DistrictName'] = data1['DistrictName'].str.lower()
    data1['WardName'] = data1['WardName'].str.lower()

    result = pd.merge(data1, data1, on=['ProvinceName', 'DistrictName', 'WardName'],
                      how='inner', suffixes=('_1', '_2'))
    result_df = result[(result['OutletID_1'] != result['OutletID_2']) & (result['OutletID_1'] < result['OutletID_2'])]
    result_df['fuzzy_similarity'] = result_df.apply(fuzzy_similarity_motfile, axis=1)
    
    matching_rows_fuzzy = result_df[result_df['fuzzy_similarity'] == 100]

    return matching_rows_fuzzy

# Thay thế những từ trùng với thông tin trong cột Optional
def replace_optional_text(row, remove_name):
    outlet_name = str(row['Outlet_Name'])  # Convert to string

    if pd.isna(outlet_name):
        return np.nan  # Skip replacement for NaN values

    for index, remove_row in remove_name.iterrows():
        optional_text = str(remove_row['Optional'])  # Ensure string conversion
        replace_text = str(remove_row['Replace'])

        outlet_name = outlet_name.replace(optional_text, replace_text)

    return outlet_name

# Loại bỏ khoảng trắng thừa
def preprocess_address(address):
    from unidecode import unidecode
    
    address = re.sub(r'\s+', ' ', address).strip()
    return unidecode(address)

# Tạo cột clean_name
def xuly_hvnname(HVN_r3, remove_name):
    HVN_r3['Outlet_Name'] = HVN_r3['OutletName'].str.lower()
    HVN_r3['Outlet_Name'].fillna('NoName', inplace=True)
    HVN_r3['Outlet_Name'].replace({None: 'NoName'}, inplace=True)
    HVN_r3['Outlet_Name'].replace({'NULL': 'NoName'}, inplace=True)
    HVN_r3['Outlet_Name'] = HVN_r3['Outlet_Name'].str.lower()

    # Tạo DataFrame chứa Outlet_Name là 'NoName'
    HVN_r3_with_NoName = HVN_r3[HVN_r3['Outlet_Name'] == 'noname']

    # Tạo DataFrame không chứa Outlet_Name là 'NoName'
    HVN_r3_without_NoName = HVN_r3[HVN_r3['Outlet_Name'] != 'noname']

    remove_name['Replace'].fillna('', inplace=True)
    remove_name['Replace'].replace({None: ''}, inplace=True)
    remove_name['Replace'].replace({'NULL': ''}, inplace=True)

    # Convert the "Replace" column in remove_name to strings
    remove_name['Replace'] = remove_name['Replace'].astype(str)

    HVN_r3_without_NoName['clean_Outlet_Name'] = HVN_r3_without_NoName.apply(lambda row: replace_optional_text(row, remove_name), axis=1)
    HVN_r3_without_NoName['clean_Outlet_Name'] = HVN_r3_without_NoName['clean_Outlet_Name'].apply(lambda x: re.sub(r'\s+', ' ', x))

    return HVN_r3_without_NoName, HVN_r3_with_NoName

def xuly_hvnname_motfile(HVN_r3, remove_name):
    HVN_r3['Outlet_Name'] = HVN_r3['OutletName'].str.lower()
    HVN_r3['Outlet_Name'].fillna('NoName', inplace=True)
    HVN_r3['Outlet_Name'].replace({None: 'NoName'}, inplace=True)
    HVN_r3['Outlet_Name'].replace({'NULL': 'NoName'}, inplace=True)
    HVN_r3['Outlet_Name'] = HVN_r3['Outlet_Name'].str.lower()

    # Tạo DataFrame chứa Outlet_Name là 'NoName'
    HVN_r3_with_NoName = HVN_r3[HVN_r3['Outlet_Name'] == 'noname']

    # Tạo DataFrame không chứa Outlet_Name là 'NoName'
    HVN_r3_without_NoName = HVN_r3[HVN_r3['Outlet_Name'] != 'noname']

    remove_name['Replace'].fillna('', inplace=True)
    remove_name['Replace'].replace({None: ''}, inplace=True)
    remove_name['Replace'].replace({'NULL': ''}, inplace=True)

    # Convert the "Replace" column in remove_name to strings
    remove_name['Replace'] = remove_name['Replace'].astype(str)

    HVN_r3_without_NoName['clean_Outlet_Name'] = HVN_r3_without_NoName.apply(lambda row: replace_optional_text(row, remove_name), axis=1)
    HVN_r3_without_NoName['clean_Outlet_Name'] = HVN_r3_without_NoName['clean_Outlet_Name'].apply(lambda x: re.sub(r'\s+', ' ', x))

    return HVN_r3_without_NoName, HVN_r3_with_NoName

def get_geoScore(Data_geo, V_geo):
    geo_dist = (distance.great_circle(Data_geo, V_geo).meters)  # higher = worse score

    #   normalize geo_scores where 0m is 100 points and >= 1000m is 0 points
    geo_score = 0
    if (geo_dist > 1000):
        geo_score = 0
    else:
        geo_score = 100 - (geo_dist / 1000 * 100)
    return geo_score

def calc_score_dist(df):
    HVN_geo = (df['Latitude_file1'], df['Longitude_file2'])
    Vigo_geo = (df['Latitude_file2'], df['Longitude_file2'])
    dist_score = get_geoScore(HVN_geo, Vigo_geo)
    return dist_score

def calc_score_name(df):
    return fuzz.ratio(df['clean_Outlet_Name_file1'], df['clean_Outlet_Name_file2'])

def tao_address_round3(data):
    data['WardName'].fillna('', inplace=True)
    data['WardName'].replace({None: ''}, inplace=True)
    data['WardName'].replace({'NULL': ''}, inplace=True)

    data['DistrictName'].fillna('', inplace=True)
    data['DistrictName'].replace({None: ''}, inplace=True)
    data['DistrictName'].replace({'NULL': ''}, inplace=True)
    data['CustomerAddress'] = data['CustomerAddress'].str.lower()

    data['Address'] = data['CustomerAddress'] + data['WardName'] + data['DistrictName'] + data['ProvinceName']

    Op = pd.read_excel("Op_Text_vigo.xlsx")

    Op['Replace'].fillna('', inplace=True)
    Op['Replace'].replace({None: ''}, inplace=True)
    Op['Replace'].replace({'NULL': ''}, inplace=True)

    # Vòng lặp qua từng hàng của OptionalText
    for index, row in Op.iterrows():
        optional_text = row['Optional']
        replace_text = row['Replace']
        
        # Check if replace_text is a string
        if not isinstance(replace_text, str):
            # Convert replace_text to string or handle accordingly
            replace_text = str(replace_text)

        # Thực hiện thay thế trong cột 'Address' của HVN
        data['Address'] = data['Address'].str.replace(optional_text, replace_text)

    data['Address'] = data['Address'].apply(lambda x: re.sub(r'[^a-z0-9\s/]', '', x))
    data['Address'] = data['Address'].apply(lambda x: re.sub(r'\s', '', x))
    return data

def overall_score(data1_Outlet_Cleaned_Name, data2_Outlet_Cleaned_Name, data1_geo, data2_geo, data1_Address, data2_Address):
    if ((data1_Outlet_Cleaned_Name == 'khong') | (data2_Outlet_Cleaned_Name == 'khong') |
        (data1_Outlet_Cleaned_Name == 'nan') | (data2_Outlet_Cleaned_Name == 'nan') |
        (data1_Outlet_Cleaned_Name == '') | (data2_Outlet_Cleaned_Name == '')
       ):
        name_score = 0
    else:    
        name_score = fuzz.ratio(data1_Outlet_Cleaned_Name, data2_Outlet_Cleaned_Name)
        
    geo_dist = (distance.great_circle(data1_geo, data2_geo).meters)
    
    if (geo_dist > 1000):
        geo_score = 0
    else:
        geo_score = 100 - (geo_dist / 1000 * 100)
    
    address_score = fuzz.ratio(data1_Address, data2_Address)
    
    score = name_score*4 + address_score*3 + geo_score*3
    return score
    
def calc_overall_score(df):
    HVN_geo = (df['Latitude_file1'], df['Longitude_file2'])
    Vigo_geo = (df['Latitude_file2'], df['Longitude_file2'])
    score = overall_score(df['clean_Outlet_Name_file1'], df['clean_Outlet_Name_file2'], HVN_geo, Vigo_geo, df['Address_file1'], df['Address_file2'])
    return score/10

def round3(HVN_r3, Vigo_r3):
    HVN_r3['ProvinceName'] = HVN_r3['ProvinceName'].str.lower()
    HVN_r3['DistrictName'] = HVN_r3['DistrictName'].str.lower()
    HVN_r3['WardName'] = HVN_r3['WardName'].str.lower()
    Vigo_r3['ProvinceName'] = Vigo_r3['ProvinceName'].str.lower()
    Vigo_r3['DistrictName'] = Vigo_r3['DistrictName'].str.lower()
    Vigo_r3['WardName'] = Vigo_r3['WardName'].str.lower()
    
    result = pd.merge(HVN_r3, Vigo_r3, left_on=['ProvinceName', 'DistrictName', 'WardName'],
                    right_on=['ProvinceName', 'DistrictName', 'WardName'], how='inner',  suffixes=('_file1', '_file2'))

    if result.empty:
        overall85storename100 = result
    else:
        result['Score_Overall'] = result.apply(calc_overall_score, axis=1)
        result['Score_Name'] = result.apply(calc_score_name, axis=1)
        overall85storename100 = result.loc[(result['Score_Overall'] >= 85) & (result['Score_Name'] == 100)]
    
    return overall85storename100

def calc_score_dist_motfile(df):
    HVN_geo = (df['Latitude_1'], df['Longitude_2'])
    Vigo_geo = (df['Latitude_2'], df['Longitude_2'])
    dist_score = get_geoScore(HVN_geo, Vigo_geo)
    return dist_score

def calc_score_name_motfile(df):
    return fuzz.ratio(df['clean_Outlet_Name_1'], df['clean_Outlet_Name_2'])

def calc_overall_score_motfile(df):
    HVN_geo = (df['Latitude_1'], df['Longitude_2'])
    Vigo_geo = (df['Latitude_2'], df['Longitude_2'])
    score = overall_score(df['clean_Outlet_Name_1'], df['clean_Outlet_Name_2'], HVN_geo, Vigo_geo, df['Address_1'], df['Address_2'])
    return score/10

def round3_motfile(HVN_r3):
    HVN_r3['ProvinceName'] = HVN_r3['ProvinceName'].str.lower()
    HVN_r3['DistrictName'] = HVN_r3['DistrictName'].str.lower()
    HVN_r3['WardName'] = HVN_r3['WardName'].str.lower()
    
    result_df = pd.merge(HVN_r3, HVN_r3, on=['ProvinceName', 'DistrictName', 'WardName'], how='inner', suffixes=('_1', '_2'))
    result_df = result_df[(result_df['OutletID_1'] != result_df['OutletID_2']) & (result_df['OutletID_1'] < result_df['OutletID_2'])]

    if result_df.empty:
        overall85storename100 = result_df
    else:    
        result_df['Score_Overall'] = result_df.apply(calc_overall_score_motfile, axis=1)
        result_df['Score_Name'] = result_df.apply(calc_score_name_motfile, axis=1)
        overall85storename100 = result_df.loc[(result_df['Score_Overall'] >= 85) & (result_df['Score_Name'] == 100)]
    
    return overall85storename100

# Hàm tính khoảng cách giữa hai điểm dựa trên tọa độ Latitude và Longitude (theo mét)
def calculate_distance(point1, point2):
    return geodesic(point1, point2).meters

def calc_score_name_2(df):
    return fuzz.token_set_ratio(df['clean_Outlet_Name_file1'], df['clean_Outlet_Name_file2'])

def calc_score_address(df):
    return fuzz.token_set_ratio(df['Address_file1'], df['Address_file2'])

def filter_distance(row):
    if 'phường' in row['WardName_file1'] and 'thành phố' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return row['distance'] <= 15 
    elif 'xã' in row['WardName_file1'] and 'thành phố' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'thị trấn' in row['WardName_file1'] and 'thành phố' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'xã' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'thị trấn' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'phường' in row['WardName_file1'] and 'thị xã' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'xã' in row['WardName_file1'] and 'thị xã' in row['DistrictName_file1'] and 'tỉnh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'xã' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_file1'] and 'quận' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'xã' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'thị trấn' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_file1'] and 'thành phố' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'phường' in row['WardName_file1'] and 'thị xã' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'xã' in row['WardName_file1'] and 'thị xã' in row['DistrictName_file1'] and 'thành phố' in row['ProvinceName_file1']:
        return  row['distance'] <= 15   
    elif 'xã' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_file1'] and 'quận' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'xã' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'thị trấn' in row['WardName_file1'] and 'huyện' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_file1'] and 'thành phố' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'phường' in row['WardName_file1'] and 'thị xã' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'xã' in row['WardName_file1'] and 'thị xã' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    
    elif 'phuong' in row['WardName_file1'] and 'thanh pho' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return row['distance'] <= 15 
    elif 'xa' in row['WardName_file1'] and 'thanh pho' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'thi tran' in row['WardName_file1'] and 'thanh pho' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'xa' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'thi tran' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'phuong' in row['WardName_file1'] and 'thi xa' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'xa' in row['WardName_file1'] and 'thi xa' in row['DistrictName_file1'] and 'tinh' in row['ProvinceName_file1']:
        return  row['distance'] <= 20
    elif 'xa' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_file1'] and 'quan' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'xa' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'thi tran' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_file1'] and 'thanh pho' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'phuong' in row['WardName_file1'] and 'thi xa' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'xa' in row['WardName_file1'] and 'thi xa' in row['DistrictName_file1'] and 'thanh pho' in row['ProvinceName_file1']:
        return  row['distance'] <= 15   
    elif 'xa' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_file1'] and 'quan' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'xa' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'thi tran' in row['WardName_file1'] and 'huyen' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_file1'] and 'thanh pho' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 10
    elif 'phuong' in row['WardName_file1'] and 'thi xa' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    elif 'xa' in row['WardName_file1'] and 'thi xa' in row['DistrictName_file1'] and 'city' in row['ProvinceName_file1']:
        return  row['distance'] <= 15
    
def round4(HVN_r4, Vigo_r4):
    # Tạo danh sách để lưu trữ dòng dữ liệu khớp
    result_rows = []
    matched_indices = set()  # Danh sách các chỉ số đã được khớp trong Vigo_r4

    # Matching cho DataFrame thứ nhất (df1)
    for index1, row1 in HVN_r4.iterrows():
        match_found = False
        for index2, row2 in Vigo_r4.iterrows():
            if index2 in matched_indices:
                continue  # Bỏ qua dòng đã được khớp trước đó trong Vigo_r4
            if (
                row1['ProvinceName'] == row2['ProvinceName'] and
                row1['DistrictName'] == row2['DistrictName'] and
                row1['WardName'] == row2['WardName']
            ):
                result_rows.append({
                    f"{col}_file1": row1[col] for col in HVN_r4.columns
                })
                result_rows[-1].update({
                    f"{col}_file2": row2[col] for col in Vigo_r4.columns
                })
                match_found = True
                matched_indices.add(index2)  # Đánh dấu dòng trong Vigo_r4 đã được khớp
                break

        if not match_found:
            # Nếu không tìm thấy match, bạn có thể xử lý theo ý của mình
            pass

    # Tạo DataFrame kết quả từ danh sách
    merged_df = pd.DataFrame(result_rows)

    if merged_df.empty:
        name80address80 = merged_df
    else:   
        merged_df['distance'] = merged_df.apply(lambda row: calculate_distance((row['Latitude_file1'], row['Longitude_file1']),
                                                                    (row['Latitude_file2'], row['Longitude_file2'])), axis=1)
        filtered_result = merged_df.apply(filter_distance, axis=1)
        filtered_result = merged_df[filtered_result]
        filtered_result['Score_Name_2'] = filtered_result.apply(calc_score_name_2, axis=1)
        filtered_result['Score_Address'] = filtered_result.apply(calc_score_address, axis=1)
        name80address80 = filtered_result.loc[(filtered_result['Score_Name_2'] >= 80) & (filtered_result['Score_Address'] >= 80)]

    return name80address80

def calc_score_name_motfile_2(df):
    return fuzz.token_set_ratio(df['clean_Outlet_Name_1'], df['clean_Outlet_Name_2'])

def apply_filter_motfile(row):
    if 'phường' in row['WardName_1'] and 'thành phố' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return row['distance'] <= 15 
    elif 'xã' in row['WardName_1'] and 'thành phố' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'thị trấn' in row['WardName_1'] and 'thành phố' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'xã' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'thị trấn' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'phường' in row['WardName_1'] and 'thị xã' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'xã' in row['WardName_1'] and 'thị xã' in row['DistrictName_1'] and 'tỉnh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'xã' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_1'] and 'quận' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'xã' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'thị trấn' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_1'] and 'thành phố' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'phường' in row['WardName_1'] and 'thị xã' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'xã' in row['WardName_1'] and 'thị xã' in row['DistrictName_1'] and 'thành phố' in row['ProvinceName_1']:
        return  row['distance'] <= 15   
    elif 'xã' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_1'] and 'quận' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'xã' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'thị trấn' in row['WardName_1'] and 'huyện' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phường' in row['WardName_1'] and 'thành phố' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'phường' in row['WardName_1'] and 'thị xã' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'xã' in row['WardName_1'] and 'thị xã' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    
    elif 'phuong' in row['WardName_1'] and 'thanh pho' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return row['distance'] <= 15 
    elif 'xa' in row['WardName_1'] and 'thanh pho' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'thi tran' in row['WardName_1'] and 'thanh pho' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'xa' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'thi tran' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'phuong' in row['WardName_1'] and 'thi xa' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'xa' in row['WardName_1'] and 'thi xa' in row['DistrictName_1'] and 'tinh' in row['ProvinceName_1']:
        return  row['distance'] <= 20
    elif 'xa' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_1'] and 'quan' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'xa' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'thi tran' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_1'] and 'thanh pho' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'phuong' in row['WardName_1'] and 'thi xa' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'xa' in row['WardName_1'] and 'thi xa' in row['DistrictName_1'] and 'thanh pho' in row['ProvinceName_1']:
        return  row['distance'] <= 15   
    elif 'xa' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_1'] and 'quan' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'xa' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'thi tran' in row['WardName_1'] and 'huyen' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'phuong' in row['WardName_1'] and 'thanh pho' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 10
    elif 'phuong' in row['WardName_1'] and 'thi xa' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    elif 'xa' in row['WardName_1'] and 'thi xa' in row['DistrictName_1'] and 'city' in row['ProvinceName_1']:
        return  row['distance'] <= 15
    
def calc_score_address_motfile(df):
    return fuzz.token_set_ratio(df['Address_1'], df['Address_2'])
    
def round4_motfile(HVN_r4):
    # Tạo danh sách để lưu trữ dòng dữ liệu khớp
    result_rows = []
    matched_indices = set()
    
    # Matching cho DataFrame thứ nhất (df1)
    for index1, row1 in HVN_r4.iterrows():
        match_found = False
        for index2, row2 in HVN_r4.iterrows():
            if index2 in matched_indices:
                continue 
            if (
                row1['ProvinceName'] == row2['ProvinceName'] and
                row1['DistrictName'] == row2['DistrictName'] and
                row1['WardName'] == row2['WardName'] and
                index1 != index2  # Kiểm tra để loại bỏ so sánh với chính nó
            ):
                result_rows.append({
                    f"{col}_1": row1[col] for col in HVN_r4.columns
                })
                result_rows[-1].update({
                    f"{col}_2": row2[col] for col in HVN_r4.columns
                })
                match_found = True
                matched_indices.add(index2)
                break

        if not match_found:
            # Nếu không tìm thấy match, bạn có thể xử lý theo ý của mình
            pass

    # Tạo DataFrame kết quả từ danh sách
    merged_df = pd.DataFrame(result_rows)
    merged_df = merged_df[(merged_df['OutletID_1'] != merged_df['OutletID_2']) & (merged_df['OutletID_1'] < merged_df['OutletID_2'])]

    if merged_df.empty:
        name80address80 = merged_df
    else:   
        merged_df['distance'] = merged_df.apply(lambda row: calculate_distance((row['Latitude_1'], row['Longitude_1']),
                                                                    (row['Latitude_2'], row['Longitude_2'])), axis=1) 
        filtered_result = merged_df.apply(apply_filter_motfile, axis=1)
        filtered_result = merged_df[filtered_result]
        filtered_result['Score_Name_2'] = filtered_result.apply(calc_score_name_motfile_2, axis=1)
        filtered_result['Score_Address'] = filtered_result.apply(calc_score_address_motfile, axis=1)
        name80address80 = filtered_result.loc[(filtered_result['Score_Name_2'] >= 80) & (filtered_result['Score_Address'] >= 80)]
    return name80address80

def process_uploaded_files(uploaded_files):
    dataframes = {}
    HVN = None
    Vigo = None

    for idx, file in enumerate(uploaded_files):
        df = pd.read_excel(file)

        # Convert "Phone" column to string
        if 'Phone' in df.columns:
            df['Phone'] = df['Phone'].astype(str)

        # Get the filename without extension
        filename_without_extension = file.name.split('.')[0]

        # Assign dataframe to dictionary using filename as key
        dataframes[filename_without_extension] = df

        # Assign specific dataframes
        if idx == 0:
            HVN = df.copy()
        elif idx == 1:
            Vigo = df.copy()

    return dataframes, HVN, Vigo

def apply_round1(HVN, Vigo, teleco1, teleco2, user_input):
    # Xử lý phone
    HVN_nophone, Vigo_nophone, HVN_phone_na, HVN_phone_notna, Vigo_phone_na, Vigo_phone_notna = xuly_phone(HVN, Vigo)
    HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa = tao_danh_sach_thoa_khongthoa(teleco1, teleco2, HVN_phone_notna, Vigo_phone_notna, HVN_nophone, HVN_phone_na, Vigo_nophone, Vigo_phone_na)
    phonenum_map = round1(HVN_thoa, Vigo_thoa, user_input)
    return phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa

def apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2):
    HVN_r2_thoa, HVN_r2_khonghtoa = loc_hvn_r2(HVN)
    vigo = xuly_toadotrongaddress_vigo(Vigo)
    vigo_r2_thoa, vigo_r2_khongthoa = loc_vigo_r2(vigo)
    df1 = xuly_address_hvn(OptionalText, HVN_r2_thoa, text_remove)
    df2 = xuly_address_Vigo(OptionalText, vigo_r2_thoa, text_remove_2)
    df1 = tao_address(df1)
    df2 = tao_address(df2)
    matching_address = round2(df1, df2)  
    return matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa

def apply_round1_motfile(HVN, teleco1, teleco2, user_input):
    HVN_nophone, HVN_phone_na, HVN_phone_notna = xuly_phone_motfile(HVN)
    HVN_thoa, HVN_khongthoa = tao_danh_sach_thoa_khongthoa_motfile(teleco1, teleco2, HVN_phone_notna, HVN_nophone, HVN_phone_na)
    phonenum_map = round1_motfile(HVN_thoa, user_input)
    return phonenum_map , HVN_thoa, HVN_khongthoa

def apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2):
    HVN_r2_thoa, HVN_r2_khonghtoa = loc_hvn_r2(HVN)
    df1 = xuly_address_hvn(OptionalText, HVN_r2_thoa, text_remove)
    df1 = tao_address(df1)
    matching_address = round2_motfile(df1)  
    return matching_address, df1, HVN_r2_khonghtoa

def main():
    # Load the image
    image = Image.open("8134648.png")

    # Resize the image to a smaller size (optional)
    image = image.resize((50, 50))

    # Use columns to place image and option_menu side by side
    col1, col2 = st.columns([1, 2])  # Adjust the ratio here

    # Display the image in the first column
    col1.image(image, use_column_width=False, width=50)
    
    st.markdown("<h1 style='text-align: center; font-size: 55px;'>Store Mapping</h1>", unsafe_allow_html=True)

    # Upload files
    st.header("1. Upload Excel File(s)")

    # Kiểm tra số lượng file đã tải lên
    uploaded_files = st.file_uploader("Upload Excel files", type=["xlsx"], accept_multiple_files=True)
    
    # Giới hạn số lượng file upload không quá 2
    MAX_FILES = 2
    if uploaded_files and len(uploaded_files) > MAX_FILES:
        st.warning(f"You can only upload up to {MAX_FILES} files. All uploaded files will be removed.")
        uploaded_files = None  # Xóa tất cả file đã upload trước đó

    # Hiển thị thông tin về file đã upload
    if uploaded_files:
        st.write("Uploaded files:")
        for uploaded_file in uploaded_files:
            st.write(uploaded_file.name)
    
    dataframes = {}
    HVN = None
    Vigo = None

    if uploaded_files:
        dataframes, HVN, Vigo = process_uploaded_files(uploaded_files)

    # Display Round table
    st.header("2. Round Table")

    # Create Round Table
    Round_table = pd.DataFrame({
        'Round': [1, 2, 3, 4],
        'Description': ['Mapping 100% phone and distance <= threshold value', 'Mapping 100% address', 
                        'Mapping ward_district_province, mapping 100% storname and mapping >= 85 overall score',
                        'Mapping ward_district_province, mapping location distance (urban 5m, sub urban 10m, rural 20m),\
                         mapping >= 80 store name and >= 80 score address'],
    })

    # Display the draggable Round Table
    selected_Round_indexes = st.multiselect("Select Round to Add to Flow", Round_table.index, format_func=lambda i: Round_table.loc[i, 'Description'], key='selected_Round')

    # Create Flow Table
    flow_table = pd.DataFrame(columns=['Round', 'Description'])

    # Update Flow Table based on the selected Round in Round Table
    if selected_Round_indexes:
        selected_Round = Round_table.loc[selected_Round_indexes]
        flow_table = pd.concat([flow_table, selected_Round])

    # Display the Flow Table
    st.header("3. Flow Table")
    st.table(flow_table)

    # Display the Flow Table
    st.header("4. Result")
    rounds = flow_table['Round'].tolist()
    
    if HVN is not None and Vigo is not None:   
        Province, teleco1, teleco2, OptionalText, text_remove, text_remove_2, remove_name, remove_name_2 = read_file()          
        # st.text("Conditions are being considered!")
        HVN = xet_latlng(HVN)
        Vigo = xet_latlng(Vigo)
        test = xet_phancap(HVN, Province)
        test2 = xet_phancap(Vigo, Province)
        
        if rounds == [1]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):               
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)

                if phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given condition</h3>', unsafe_allow_html=True)
                else:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
        
        elif rounds == [2]:
            if st.button("Apply"):                
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)               

                if matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given condition</h3>', unsafe_allow_html=True)
                else:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                            
        elif rounds == [3]:
            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)          
                overall85storename100 = round3(HVN_address, Vigo_address)

                if overall85storename100.empty:   
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given condition</h3>', unsafe_allow_html=True)
                else:   
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                           
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [4]:
            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given condition</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    distance_df_2['level'] = 4.2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df_2)
                     
                elif distance_df_2.empty:
                    distance_df['level'] = 4.1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)                                                            
                else:                        
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif  rounds == [1, 2]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                    
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                    
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)                      
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)  
                                
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                                    
        elif rounds == [1, 3]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])

                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)      
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName) 
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                        
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)   
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [1, 4]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                                                     
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and distance_df_2.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty and distance_df_2.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                            
                elif distance_df_2.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                               
                else:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [2, 1]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                           
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if matching_address.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True) 
                    st.dataframe(phonenum_map)
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)      
                else:         
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                                        
        elif rounds == [2, 3]:
            if st.button("Apply"):                
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])
                            
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)    
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)               
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                else:                       
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                            
        elif rounds == [2, 4]:
            if st.button("Apply"):                 
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)    

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and distance_df.empty and distance_df_2.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty and distance_df_2.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                elif distance_df.empty:
                    matching_address['level'] = 2
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                           
                elif distance_df_2.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([matching_address, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [3, 1]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                else: 
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua) 
                                
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [3, 2]:
            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)         
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                     
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)    
                else:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [3, 4]:
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r2, HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and distance_df.empty and distance_df_2.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)  
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([overall85storename100, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                elif distance_df_2.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)    
                                
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [4, 1]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                                             
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.subheader("Displaying file 1 after checking phone:")
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(phonenum_map)  

                if distance_df.empty and distance_df_2.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)   
                elif distance_df.empty and distance_df_2.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                elif distance_df.empty and phonenum_map.empty:
                    distance_df_2['level'] = 4.2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df_2)                     
                elif distance_df_2.empty and phonenum_map.empty:
                    distance_df['level'] = 4.1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)
                elif phonenum_map.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                              
                else:   
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                        
        elif rounds == [4, 2]:
            if st.button("Apply"):                                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty and distance_df_2.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                elif distance_df.empty and matching_address.empty:
                    distance_df_2['level'] = 4.2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df_2)                   
                elif distance_df_2.empty and matching_address.empty:
                    distance_df['level'] = 4.1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)
                elif matching_address.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:   
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level']= 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 3]:
            if st.button("Apply"):                                     
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]      
                                            
                overall85storename100 = round3(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty and distance_df_2.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100) 
                elif distance_df.empty and overall85storename100.empty:
                    distance_df_2['level'] = 4.2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df_2)                       
                elif distance_df_2.empty and overall85storename100.empty:
                    distance_df['level'] = 4.1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)
                elif overall85storename100.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                     
                else:   
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [1, 2, 3]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                     
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])
                            
                # Xử lý name, address

                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)    
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                        
                if phonenum_map.empty and matching_address.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:      
                    phonenum_map['level'] = 1                 
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])                
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif  rounds == [1, 2, 4]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                     
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])
                    
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and matching_address.empty and distance_df.empty and distance_df_2.empty:                    
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                     
                elif distance_df_2.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])                       
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif  rounds == [1, 3, 2]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)   
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                                        
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:   
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and overall85storename100.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                             
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [1, 3, 4]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)                
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                                        
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                                    
                distance_df = round4(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r3, HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and overall85storename100.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                elif distance_df_2.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)            
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                            
        elif rounds == [1, 4, 2]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"): 
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                        
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
    
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and distance_df_2.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, distance_df])                        
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:
                    phonenum_map['level'] = 1 
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level']= 2
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [1, 4, 3]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                        
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                                                      
                overall85storename100 = round3(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                        
                if phonenum_map.empty and distance_df.empty and distance_df_2.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                              
                else:
                    phonenum_map['level'] = 1   
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [2, 1, 3]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                              
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)    

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])

                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)     
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                                        
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                            
        elif rounds == [2, 1, 4]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                              
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])

                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                elif distance_df_2.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                            
        elif rounds == [2, 3, 1]:
            # Slicer for user_input
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):            
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)  

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])
                            
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)    
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                                           
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    matching_address['level'] =1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [2, 3, 4]:
            if st.button("Apply"): 
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)     

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])
                            
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)               
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                                
                distance_df = round4(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r3, HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                elif distance_df_2.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [2, 4, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")
            if st.button("Apply"): 
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)    

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                    
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and distance_df.empty and distance_df_2.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                  
                else:  
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [2, 4, 3]:
            if st.button("Apply"):                 
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)    

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
            
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                                                    
                overall85storename100 = round3(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and distance_df.empty and distance_df_2.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                
                else:
                    matching_address['level'] = 2   
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [3, 1, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)          
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])
                        
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                   
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                    
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                        
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                                
        elif rounds == [3, 1, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):       
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)         
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])

                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                elif distance_df_2.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [3, 2, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)                
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)          
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2 
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else: 
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])

                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)      
                else:    
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)  
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")    
                                            
        elif rounds == [3, 2, 4]:
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2 
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else: 
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])
                    
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty and distance_df.empty and distance_df_2.empty:                    
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                  
                elif distance_df_2.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])                       
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [3, 4, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r2, HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df.empty:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)  

                if overall85storename100.empty and distance_df.empty and distance_df_2.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                 
                else:  
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [3, 4, 2]:
            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)                
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r2, HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df.empty:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)                

                if overall85storename100.empty and distance_df.empty and distance_df_2.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([overall85storename100, distance_df])                        
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level']= 2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 1, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):        
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)  

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r2, Vigo_khongthoa])
                        
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and phonenum_map.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                   
                elif matching_address.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                   
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 1, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):        
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True) 

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])
                    
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)                     
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and phonenum_map.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                            
        elif rounds == [4, 2, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                                        
                if distance_df.empty and distance_df_2.empty and matching_address.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)       
                else:    
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [4, 2, 3]:
            if st.button("Apply"):         
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])

                # Xử lý name, address
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)     
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and matching_address.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:      
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2                
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])  
                    ket_qua = pd.concat([ket_qua, overall85storename100])                 
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                            
        elif rounds == [4, 3, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]           
                                            
                overall85storename100 = round3(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)  

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)               

                if distance_df.empty and distance_df_2.empty and overall85storename100.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [4, 3, 2]:
            if st.button("Apply"):          
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]          
                                            
                overall85storename100 = round3(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)   

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and overall85storename100.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                             
                elif matching_address.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2                        
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2 
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")    
                                            
        elif rounds == [1, 2, 3, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                     
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])
                            
                # Xử lý name, address

                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)                   
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                    
                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r4 = HVN_address
                    Vigo_r4= Vigo_address
                else: 
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r4, Vigo_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r4, HVN_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and matching_address.empty and overall85storename100.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                elif distance_df_2.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [1, 2, 4, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):         
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                    
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])
                                    
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)              
                        
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_address
                    Vigo_r4= Vigo_address
                elif distance_df.empty:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]           
                                            
                overall85storename100 = round3(HVN_r4, Vigo_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and matching_address.empty and distance_df.empty and distance_df_2.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2   
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [1, 3, 2, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)        
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                        
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:   
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round2
                if matching_address.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3 
                else:
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    Vigo_r4 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, vigo_r2_khongthoa])  
                    
                # Xử lý name
                HVN_r5, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_r5, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r5)                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)  

                if phonenum_map.empty and overall85storename100.empty and matching_address.empty and distance_df.empty and distance_df_2.empty:                    
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                   
                elif distance_df_2.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address]) 
                    ket_qua = pd.concat([ket_qua, distance_df])                      
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif  rounds == [1, 3, 4, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)                
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r3, HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                    HVN_r4 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df.empty:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                else:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r4, Vigo_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and overall85storename100.empty and distance_df.empty and distance_df_2.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([phonenum_map, overall85storename100])                        
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                       
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level']= 2
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [1, 4, 2, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
   
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round2
                if matching_address.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3 
                else:
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    Vigo_r4 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, vigo_r2_khongthoa])

                # Xử lý name, address
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)      
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and distance_df_2.empty and matching_address.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    phonenum_map['level'] = 1      
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2                
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2]) 
                    ket_qua = pd.concat([ket_qua, matching_address])  
                    ket_qua = pd.concat([ket_qua, overall85storename100])                 
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                            
        elif rounds == [1, 4, 3, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN, Vigo, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r2 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_khongthoa])
                          
                # Xử lý name
                HVN_r3, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r3, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r3)
                Vigo_address = tao_address_round3(Vigo_r3)
            
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_address
                    Vigo_r4= Vigo_address
                elif distance_df.empty:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]         
                                            
                overall85storename100 = round3(HVN_r4, Vigo_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r5 = HVN_r4
                    Vigo_r5= Vigo_r4
                    HVN_r5 = pd.concat([HVN_r5, HVN_with_NoName])
                    Vigo_r5 = pd.concat([Vigo_r5, Vigo_with_NoName])
                else:
                    HVN_r5 = HVN_r4.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r5 = Vigo_r4.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r5 = pd.concat([HVN_r5, HVN_with_NoName])
                    Vigo_r5 = pd.concat([Vigo_r5, Vigo_with_NoName])
                    
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r5, Vigo_r5, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and distance_df_2.empty and overall85storename100.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                              
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2                        
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2 
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                            
        elif rounds == [2, 1, 3, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):              
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])
                    
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)    

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])

                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)                
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                                 
                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r4 = HVN_address
                    Vigo_r4= Vigo_address
                else: 
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r4, Vigo_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r4, HVN_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and overall85storename100.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
         
                elif distance_df_2.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                            
        elif rounds == [2, 1, 4, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])
              
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
        
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_address
                    Vigo_r4= Vigo_address
                elif distance_df.empty:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                                     
                overall85storename100 = round3(HVN_r4, Vigo_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and distance_df.empty and distance_df_2.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                       
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                         
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                            
        elif rounds == [2, 3, 1, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"): 
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)    

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])
                            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)     
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                        
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)       

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                else:                        
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    Vigo_r4 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_khongthoa])
       
                # Xử lý name
                HVN_r5, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_r5, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r5)
                Vigo_address = tao_address_round3(Vigo_r5)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and phonenum_map.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                
                elif distance_df.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                elif distance_df_2.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
          
                else:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                            
        elif rounds == [2, 3, 4, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):     
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)     

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])
                            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                         
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r3, HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                elif distance_df.empty:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                else:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                    
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r4, Vigo_r4, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and distance_df.empty and distance_df_2.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                 
                else:  
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [2, 4, 1, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")
            if st.button("Apply"): 
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)     

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3
                else:
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    Vigo_r4 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_khongthoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                     
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and distance_df.empty and distance_df_2.empty and phonenum_map.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                   
                else:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [2, 4, 3, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")
            if st.button("Apply"):         
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN, Vigo, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                else:
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    Vigo_r2 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r2 = pd.concat([Vigo_r2, vigo_r2_khongthoa])

                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r2, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r2, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
 
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_address
                    Vigo_r3= Vigo_address
                elif distance_df.empty:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                                            
                overall85storename100 = round3(HVN_r3, Vigo_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                else:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r4 = Vigo_r3.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r4, Vigo_r4, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and distance_df.empty and distance_df_2.empty and overall85storename100.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [3, 1, 2, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)     
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)          
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])
                        
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2
                if matching_address.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3 
                else:
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    Vigo_r4 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, vigo_r2_khongthoa])
  
                # Xử lý name
                HVN_r5, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_r5, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r5)
                Vigo_address = tao_address_round3(Vigo_r5)
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty and matching_address.empty and distance_df.empty and distance_df_2.empty:                    
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                 
                elif distance_df_2.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])                        
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                        
        elif rounds == [3, 1, 4, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)         
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                    
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])
                               
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                elif distance_df.empty:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r4, Vigo_r4, OptionalText, text_remove, text_remove_2)
 
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(matching_address)

                if overall85storename100.empty and phonenum_map.empty and distance_df.empty and distance_df_2.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([overall85storename100, phonenum_map])                        
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1 
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level']= 2
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])    
                    ket_qua = pd.concat([ket_qua, matching_address])                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                
        elif rounds == [3, 2, 1, 4]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)     
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)         
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2 
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else: 
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input) 
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3
                else:
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    Vigo_r4 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_khongthoa])
                                  
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
 

                if overall85storename100.empty and matching_address.empty and phonenum_map.empty and distance_df.empty and distance_df_2.empty:                  
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                elif distance_df_2.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [3, 2, 4, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo 
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2) 
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2 
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else: 
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])
                                
                # Xử lý name
                HVN_r4, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_r4, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_r4)
                Vigo_address = tao_address_round3(Vigo_r4)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4
                if distance_df.empty and distance_df_2.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                elif distance_df.empty:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r4, Vigo_r4, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty and distance_df.empty and distance_df_2.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                              
                else:  
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [3, 4, 1, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)   
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r2, HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
 
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df.empty:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3
                else:
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    Vigo_r4 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_khongthoa])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r4, Vigo_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)                   

                if overall85storename100.empty and distance_df.empty and distance_df_2.empty and phonenum_map.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                   
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)               
                else:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [3, 4, 2, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")        
            if st.button("Apply"):        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)   
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)      
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                
                distance_df = round4(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_r2, HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
 
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df.empty:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3
                else:
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    Vigo_r4 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r4, Vigo_r4, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if overall85storename100.empty and distance_df.empty and distance_df_2.empty and matching_address.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)      
                else:    
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 1, 2, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):               
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
 
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input) 
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)   

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r2, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r2, Vigo_khongthoa])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                # Loại bỏ data thỏa round2
                if matching_address.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3 
                else:
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    Vigo_r4 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, vigo_r2_khongthoa])  
                            
                # Xử lý name, address
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                 
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                        
                if distance_df.empty and distance_df_2.empty and phonenum_map.empty and matching_address.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2      
                    phonenum_map['level'] = 1                 
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])  
                    ket_qua = pd.concat([ket_qua, matching_address]) 
                    ket_qua = pd.concat([ket_qua, overall85storename100])          
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")

        elif rounds == [4, 1, 3, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r2, Vigo_r2, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2
                else:
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    Vigo_r3 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                        
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3
                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                else:   
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                    
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r4, Vigo_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 
    
                if distance_df.empty and distance_df_2.empty and phonenum_map.empty and overall85storename100.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                             
                elif matching_address.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 2, 1, 3]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                      
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
                
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3
                else:
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    Vigo_r4 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_khongthoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r4, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r4, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                     
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                
                if distance_df.empty and distance_df_2.empty and matching_address.empty and phonenum_map.empty and overall85storename100.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)           
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 2, 3, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")
            if st.button("Apply"):         
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)

                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN
                    Vigo_r2= Vigo
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    Vigo_r2 = pd.concat([Vigo_r2, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r2, Vigo_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 2   
                if matching_address.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3 = Vigo_r2 
                else:
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                    Vigo_r3 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r3 = pd.concat([Vigo_r3, vigo_r2_khongthoa])

                # Xử lý name, address
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN_r3, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo_r3, remove_name_2)
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)                     
                overall85storename100 = round3(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r4 = Vigo_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_with_NoName])
                    
                # Xử lý phone
                phonenum_map, HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r4, Vigo_r4, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and matching_address.empty and overall85storename100.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    matching_address['level'] =1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2                        
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                            
        elif rounds == [4, 3, 1, 2]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                         
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)
 
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
                 
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]           
                                            
                overall85storename100 = round3(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                    
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r3, Vigo_r3, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)                   

                # Loại bỏ data thỏa round1
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4= Vigo_r3
                else:
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    Vigo_r4 = Vigo_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, Vigo_khongthoa])
                        
                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r4, Vigo_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and distance_df_2.empty and overall85storename100.empty and phonenum_map.empty and matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                   
                elif matching_address.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                    
                else:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                            
        elif rounds == [4, 3, 2, 1]:
            user_input = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input}m")

            if st.button("Apply"):                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname(HVN, remove_name)
                Vigo_without_NoName, Vigo_with_NoName = xuly_hvnname(Vigo, remove_name_2)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                Vigo_address = tao_address_round3(Vigo_without_NoName)          
                distance_df = round4(HVN_address, Vigo_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 1 - DONE</h4>', unsafe_allow_html=True)

                distance_df_2 = round4(Vigo_address, HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 for file 2 - DONE</h4>', unsafe_allow_html=True)
                 
                # Lọc data đã thảo round 4  
                if distance_df.empty and distance_df_2.empty:
                    HVN_r2 = HVN_address
                    Vigo_r2= Vigo_address
                elif distance_df.empty:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file2)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]
                elif distance_df_2.empty:            
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file2)]
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_file1)]
                    Vigo_r2 = Vigo_address.loc[lambda df: ~df.OutletID.isin(distance_df_2.OutletID_file1)]           
                                            
                overall85storename100 = round3(HVN_r2, Vigo_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                     
                # Lọc data đã thảo round 3  
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    Vigo_r3= Vigo_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file1)]
                    Vigo_r3 = Vigo_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_file2)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    Vigo_r3 = pd.concat([Vigo_r3, Vigo_with_NoName])

                matching_address, df1, df2, HVN_r2_khonghtoa, vigo_r2_khongthoa = apply_round2(HVN_r3, Vigo_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)
                
                # Lọc data đã thảo round 2  
                if matching_address.empty:
                    HVN_r4 = HVN_r3
                    Vigo_r4 = Vigo_r3
                else:  
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    Vigo_r4 = df2.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_file2)]
                    Vigo_r4 = pd.concat([Vigo_r4, vigo_r2_khongthoa])

                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa, Vigo_thoa, Vigo_khongthoa =apply_round1(HVN_r4, Vigo_r4, teleco1, teleco2, user_input)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True) 

                if distance_df.empty and distance_df_2.empty and overall85storename100.empty and matching_address.empty and phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2                        
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                          
                else:    
                    distance_df['level'] = 4.1
                    distance_df_2['level'] = 4.2   
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, distance_df_2])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 

    if HVN is not None and Vigo is None:
        Province, teleco1, teleco2, OptionalText, text_remove, text_remove_2, remove_name, remove_name_2 = read_file()
        # st.text("Conditions are being considered!")
        HVN = xet_latlng(HVN)
        test = xet_phancap(HVN, Province)
        
        if rounds == [1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):               
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                        
                else:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [2]:
            if st.button("Apply"): 
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)              

                if matching_address.empty:
                   st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                else:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                                            
        elif rounds == [3]:
            if st.button("Apply"):         
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)              
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty:   
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                else:   
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)               
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [4]:
            if st.button("Apply"): 
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)     
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                            
                if distance_df.empty:                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                                         
                else:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")          
                
        elif  rounds == [1, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                if phonenum_map.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)     
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)               
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                   
        elif rounds == [1, 3]:
            # Slicer for user_input
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):             
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)             
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if phonenum_map.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                         
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)        
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)    
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                           
        elif rounds == [1, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)       
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)   
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(phonenum_map)                                                                          
                else:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4

                    ket_qua = pd.concat([phonenum_map, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                             
        elif rounds == [2, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)               
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if matching_address.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)   
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)   
                else:         
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                                      
        elif rounds == [2, 3]:
            if st.button("Apply"):
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)              
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if matching_address.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                else:                       
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                                         
        elif rounds == [2, 4]:
            if st.button("Apply"):
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                if matching_address.empty and distance_df.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    matching_address['level'] = 2
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(matching_address)
                else:
                    matching_address['level'] = 2
                    distance_df['level'] = 4

                    ket_qua = pd.concat([matching_address, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [3, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):     
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)        
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                else: 
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                        
        elif rounds == [3, 2]:
            if st.button("Apply"): 
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)           
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                       
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                      
                else:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [3, 4]:
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)              
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
            
                distance_df = round4_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and distance_df.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)  
                
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(overall85storename100)
                else:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4

                    ket_qua = pd.concat([overall85storename100, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [4, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):           
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif phonenum_map.empty:
                    distance_df['level'] = 4
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)                                                               
                else:   
                    distance_df['level'] = 4
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                     
        elif rounds == [4, 2]:
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                if distance_df.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                
                elif  matching_address.empty:
                    distance_df['level'] = 4
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)                                        
                else:   
                    distance_df['level'] = 4
                    matching_address['level']= 2
                    ket_qua = pd.concat([distance_df, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                          
        elif rounds == [4, 3]:
            if st.button("Apply"):  
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                if distance_df.empty:
                    HVN_r2 = HVN_address
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                
                if distance_df.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                     
                elif overall85storename100.empty:
                    distance_df['level'] = 4
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(distance_df)                                      
                else:   
                    distance_df['level'] = 4
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                         
        elif rounds == [1, 2, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):  
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)  
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)          
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if phonenum_map.empty and matching_address.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:      
                    phonenum_map['level'] = 1                 
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])                
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)  
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif  rounds == [1, 2, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)   
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)  

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa]) 
                   
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)                        
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and matching_address.empty and distance_df.empty :                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                            
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif  rounds == [1, 3, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)          
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and overall85storename100.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                               
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [1, 3, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)             
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                            
                distance_df = round4_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and overall85storename100.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                          
        elif rounds == [1, 4, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_r2
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4
                    ket_qua = pd.concat([phonenum_map, distance_df])                        
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                     
                else:
                    phonenum_map['level'] = 1 
                    distance_df['level'] = 4
                    matching_address['level']= 2
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                           
        elif rounds == [1, 4, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_address
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if phonenum_map.empty and distance_df.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:
                    phonenum_map['level'] = 1   
                    distance_df['level'] = 4
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                          
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [2, 1, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)              
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                         
        elif rounds == [2, 1, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)    

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)
                                     
                if matching_address.empty and phonenum_map.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                
                elif distance_df.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                          
        elif rounds == [2, 3, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)             
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    matching_address['level'] =1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                         
        elif rounds == [2, 3, 4]:
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                                       
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                            
                distance_df = round4_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                
                elif distance_df.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])

                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [2, 4, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):              
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)      
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                if distance_df.empty:
                    HVN_r3 = HVN_r2
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)       
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and distance_df.empty and  phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    ket_qua = pd.concat([matching_address, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                  
                else:  
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [2, 4, 3]:
            if st.button("Apply"):              
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_address
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if matching_address.empty and distance_df.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    ket_qua = pd.concat([matching_address, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                 
                else:
                    matching_address['level'] = 2   
                    distance_df['level'] = 4
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [3, 1, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):     
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(phonenum_map)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                     
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; List of unsatisfactory Outlets:</h3>', unsafe_allow_html=True)                
                    st.dataframe(HVN_r3)                     
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                    HVN_chuachay = HVN.loc[lambda df: ~df.OutletID.isin(ket_qua.OutletID_1)]           
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; List of unsatisfactory Outlets:</h3>', unsafe_allow_html=True)                
                    st.dataframe(HVN_chuachay)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                             
        elif rounds == [3, 1, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):     
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])   

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName) 
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [3, 2, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)           
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)  

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True) 

                if overall85storename100.empty and matching_address.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)  
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)      
                else:    
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                        
        elif rounds == [3, 2, 4]:
            if st.button("Apply"): 
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)              
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty and distance_df.empty :                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                  
                else:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                          
        elif rounds == [3, 4, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)         
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)     

                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
     
                distance_df = round4_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                    
                if distance_df.empty:
                    HVN_r3 = HVN_r2
                    VN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and distance_df.empty and  phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                 
                else:  
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                       
        elif rounds == [3, 4, 2]:
            if st.button("Apply"):
                st.text("Current round is [3, 4, 2]")
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)             
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
  
                distance_df = round4_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                    
                if distance_df.empty:
                    HVN_r3 = HVN_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2) 
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)             

                if overall85storename100.empty and distance_df.empty and  matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    ket_qua = pd.concat([overall85storename100, distance_df])                        
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    matching_address['level']= 2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [4, 1, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):           
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)       
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(distance_df)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                st.dataframe(phonenum_map)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)

                if distance_df.empty and phonenum_map.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                     
                elif matching_address.empty:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                     
                else:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                           
        elif rounds == [4, 1, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):           
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)     
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)             
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if distance_df.empty and phonenum_map.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)               
                else:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                          
        elif rounds == [4, 2, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)     
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)  
                                       
                if distance_df.empty and matching_address.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)   
                elif phonenum_map.empty:
                    distance_df['level'] = 4
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)      
                else:    
                    distance_df['level'] = 4
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                           
        elif rounds == [4, 2, 3]:
            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)   
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)              
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)       

                if distance_df.empty and matching_address.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    distance_df['level'] = 4
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:      
                    distance_df['level'] = 4               
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([distance_df, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])                 
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                          
        elif rounds == [4, 3, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"): 
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN_address
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else: 
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)         
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)               

                if distance_df.empty and  overall85storename100.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([distance_df, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [4, 3, 2]:
            if st.button("Apply"):  
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)  
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN_address
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
             
                overall85storename100 = round3_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else: 
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and  overall85storename100.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                               
                elif matching_address.empty:
                    distance_df['level'] = 4                       
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([distance_df, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                        
        elif rounds == [1, 2, 3, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)        
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r4 = HVN_address
                else: 
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                      
                distance_df = round4_motfile(HVN_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and matching_address.empty and overall85storename100.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                    
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4

                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [1, 2, 4, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                # Xử lý phone
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa]) 
                   
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r4 = HVN_address
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if phonenum_map.empty and matching_address.empty and distance_df.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                               
                else:
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2   
                    distance_df['level'] = 4
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([phonenum_map, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [1, 3, 2, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):              
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)          
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True) 

                if matching_address.empty:
                    HVN_r4 = HVN_r3
                else:    
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty and overall85storename100.empty and matching_address.empty and distance_df.empty :                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif distance_df.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                                   
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4

                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [1, 3, 4, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    # Lọc data cho round2 
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)           
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]              
                            
                distance_df = round4_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r4 = HVN_r3
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                else:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)             

                if phonenum_map.empty and overall85storename100.empty and distance_df.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    ket_qua = pd.concat([phonenum_map, overall85storename100])                        
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                         
                else:
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    matching_address['level']= 2
                    ket_qua = pd.concat([phonenum_map, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                           
        elif rounds == [1, 4, 2, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
                
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_r2
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r4 = HVN_r3
                else:    
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)        
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and  matching_address.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4
                    matching_address['level'] = 2
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1      
                    distance_df['level'] = 4               
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])  
                    ket_qua = pd.concat([ket_qua, overall85storename100])                 
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                         
        elif rounds == [1, 4, 3, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")

            if st.button("Apply"):            
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r2 = HVN
                else:  
                    HVN_r2 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_khongthoa])
    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)       
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_address
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                else: 
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty and distance_df.empty and overall85storename100.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                               
                elif matching_address.empty:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4                       
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4 
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([phonenum_map, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                         
        elif rounds == [2, 1, 3, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)         
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                
                if overall85storename100.empty:
                    HVN_r4 = HVN_address
                else: 
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                            
                distance_df = round4_motfile(HVN_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and overall85storename100.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)
                
                elif distance_df.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4

                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                          
        elif rounds == [2, 1, 4, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)   

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)       
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r4 = HVN_address
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r4)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and phonenum_map.empty and distance_df.empty and  overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                    
                else:
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4
                    overall85storename100['level']= 3
                    ket_qua = pd.concat([matching_address, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                        
        elif rounds == [2, 3, 1, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):             
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)          
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)     

                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                else:  
                    # Lọc data cho round2 
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                
                if matching_address.empty and overall85storename100.empty and phonenum_map.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                
                elif distance_df.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                else:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4

                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                        
        elif rounds == [2, 3, 4, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):            
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])
                    
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)           
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                                    
                if overall85storename100.empty:
                    HVN_r3 = HVN_address
                else: 
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                                        
                distance_df = round4_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r4 = HVN_r3
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                else:
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r4, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty and overall85storename100.empty and distance_df.empty and  phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                              
                else:  
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([matching_address, overall85storename100])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [2, 4, 1, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):              
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)      
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_r2
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)            
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                else:  
                    # Lọc data cho round2 
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)           
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if matching_address.empty and distance_df.empty and  phonenum_map.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                 
                else:
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [2, 4, 3, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):              
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r2 = HVN
                else:    
                    HVN_r2 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_r2_khonghtoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r2, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)                        
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r3 = HVN_address
                else:
                    HVN_r3 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r3)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                
                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                else: 
                    HVN_r4 = HVN_r3.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r4, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True) 

                if matching_address.empty and distance_df.empty and overall85storename100.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([matching_address, distance_df])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [3, 1, 2, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):     
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])   

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r4 = HVN_r3
                else:    
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa]) 
                   
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                                
                if overall85storename100.empty and phonenum_map.empty and matching_address.empty and distance_df.empty :                    
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                     
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    distance_df['level'] = 4

                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)

                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                    
        elif rounds == [3, 1, 4, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):     
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)  
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r4 = HVN_r3
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and phonenum_map.empty and distance_df.empty and  matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4
                    ket_qua = pd.concat([overall85storename100, phonenum_map])                        
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                        
                else:
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1 
                    distance_df['level'] = 4
                    matching_address['level']= 2
                    ket_qua = pd.concat([overall85storename100, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df]) 
                    ket_qua = pd.concat([ket_qua, matching_address])                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                      
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        elif rounds == [3, 2, 1, 4]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)          
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                else:  
                    # Lọc data cho round2 
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)  
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if overall85storename100.empty and matching_address.empty and phonenum_map.empty and distance_df.empty :                  
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                
                elif distance_df.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)            
                else:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    distance_df['level'] = 4

                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                          
        elif rounds == [3, 2, 4, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                   
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r4 = HVN_r3
                else:
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r4, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True) 

                if overall85storename100.empty and matching_address.empty and distance_df.empty and  phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                                                 
                else:  
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    distance_df['level'] = 4
                    phonenum_map['level']= 1
                    ket_qua = pd.concat([overall85storename100, matching_address])
                    ket_qua = pd.concat([ket_qua, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                        
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")   
                                         
        elif rounds == [3, 4, 1, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)            
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                            
                distance_df = round4_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                    
                if distance_df.empty:
                    HVN_r3 = HVN_r2
                    VN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)              
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                else:  
                    # Lọc data cho round2 
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)                 

                if overall85storename100.empty and distance_df.empty and  phonenum_map.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                     
                elif matching_address.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                   
                else:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [3, 4, 2, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m")
            if st.button("Apply"):
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)        
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r2 = HVN_address
                else: 
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                            
                distance_df = round4_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)
                    
                if distance_df.empty:
                    HVN_r3 = HVN_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else:
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)              

                if matching_address.empty:
                    HVN_r4 = HVN_r3
                else:    
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r4, teleco1, teleco2, user_input2)              
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True) 

                if overall85storename100.empty and distance_df.empty and matching_address.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)   
                elif phonenum_map.empty:
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    matching_address['level'] = 2
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)       
                else:    
                    overall85storename100['level'] = 3
                    distance_df['level'] = 4
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([overall85storename100, distance_df])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                          
        elif rounds == [4, 1, 2, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):           
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)     
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])
                    
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r4 = HVN_r3
                else:    
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)           
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                   
                if distance_df.empty and  phonenum_map.empty and matching_address.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    distance_df['level'] = 4    
                    phonenum_map['level'] = 1                 
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3

                    ket_qua = pd.concat([distance_df, phonenum_map]) 
                    ket_qua = pd.concat([ket_qua, matching_address]) 
                    ket_qua = pd.concat([ket_qua, overall85storename100])          
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")

        elif rounds == [4, 1, 3, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):           
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)   
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r2, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)  

                if phonenum_map.empty:
                    HVN_r3 = HVN_r2
                else:  
                    # Lọc data cho round2 
                    HVN_r3 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)          
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                else: 
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)
   
                if distance_df.empty and  phonenum_map.empty and overall85storename100.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                                               
                elif matching_address.empty:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else:
                    distance_df['level'] = 4
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2

                    ket_qua = pd.concat([distance_df, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [4, 2, 1, 3]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):            
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)  
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])

                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                else:  
                    # Lọc data cho round2 
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])

                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r4, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)             
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if distance_df.empty and  matching_address.empty and phonenum_map.empty and overall85storename100.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif overall85storename100.empty:
                    distance_df['level'] = 4
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)           
                else:
                    distance_df['level'] = 4
                    matching_address['level'] = 2
                    phonenum_map['level'] = 1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [4, 2, 3, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):               
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)    
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
                    HVN_r2 = pd.concat([HVN_r2, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r2, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r3 = HVN_r2
                else:    
                    HVN_r3 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_r2_khonghtoa])
                        
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN_r3, remove_name)
                HVN_address = tao_address_round3(HVN_without_NoName)              
                overall85storename100 = round3_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                     
                if overall85storename100.empty:
                    HVN_r4 = HVN_r3
                else: 
                    HVN_r4 = HVN_address.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r4, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and matching_address.empty and overall85storename100.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True) 
                elif phonenum_map.empty:
                    distance_df['level'] = 4
                    matching_address['level'] =1
                    overall85storename100['level'] = 3
                    ket_qua = pd.concat([distance_df, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                else: 
                    distance_df['level'] = 4                       
                    matching_address['level'] = 2
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1

                    ket_qua = pd.concat([distance_df, matching_address])
                    ket_qua = pd.concat([ket_qua, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")  
                                          
        elif rounds == [4, 3, 1, 2]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"): 
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)      
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN_address
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]

                overall85storename100 = round3_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else: 
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r3, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)
                
                if phonenum_map.empty:
                    HVN_r4 = HVN_r3
                else:  
                    # Lọc data cho round2 
                    HVN_r4 = HVN_thoa.loc[lambda df: ~df.OutletID.isin(phonenum_map.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_khongthoa])
                
                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r4, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty and  overall85storename100.empty and phonenum_map.empty and matching_address.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)                     
                elif matching_address.empty:
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)                                       
                else:
                    distance_df['level'] = 4
                    overall85storename100['level'] = 3
                    phonenum_map['level'] = 1
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done") 
                                           
        elif rounds == [4, 3, 2, 1]:
            user_input2 = st.slider("Select threshold distance:", 0, 100, 50, 1)
            st.text(f"Selected distance: {user_input2}m") 
            if st.button("Apply"):             
                # Xử lý name
                HVN_without_NoName, HVN_with_NoName = xuly_hvnname_motfile(HVN, remove_name)
                # Xử lý address
                HVN_address = tao_address_round3(HVN_without_NoName)   
                distance_df = round4_motfile(HVN_address)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 4 - DONE</h4>', unsafe_allow_html=True)

                if distance_df.empty:
                    HVN_r2 = HVN_address
                else:
                    HVN_r2 = HVN_address.loc[lambda df: ~df.OutletID.isin(distance_df.OutletID_1)]
   
                overall85storename100 = round3_motfile(HVN_r2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 3 - DONE</h4>', unsafe_allow_html=True)
                 
                if overall85storename100.empty:
                    HVN_r3 = HVN_r2
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])
                else: 
                    HVN_r3 = HVN_r2.loc[lambda df: ~df.OutletID.isin(overall85storename100.OutletID_1)]
                    HVN_r3 = pd.concat([HVN_r3, HVN_with_NoName])

                matching_address, df1, HVN_r2_khonghtoa = apply_round2_motfile(HVN_r3, OptionalText, text_remove, text_remove_2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 2 - DONE</h4>', unsafe_allow_html=True)

                if matching_address.empty:
                    HVN_r4 = HVN_r3
                else:    
                    HVN_r4 = df1.loc[lambda df: ~df.OutletID.isin(matching_address.OutletID_1)]
                    HVN_r4 = pd.concat([HVN_r4, HVN_r2_khonghtoa])
                    
                phonenum_map , HVN_thoa, HVN_khongthoa = apply_round1_motfile(HVN_r4, teleco1, teleco2, user_input2)
                st.markdown('<h4 style="display:flex; align-items:center;">&hybull; Apply round 1 - DONE</h4>', unsafe_allow_html=True)   

                if distance_df.empty and  overall85storename100.empty and matching_address.empty and phonenum_map.empty:
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; There are no outlets that meet the given conditions</h3>', unsafe_allow_html=True)  
                elif phonenum_map.empty:
                    distance_df['level'] = 4                      
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)    
                else:    
                    distance_df['level'] = 4  
                    overall85storename100['level'] = 3
                    matching_address['level'] = 2    
                    phonenum_map['level'] = 1
                    ket_qua = pd.concat([distance_df, overall85storename100])
                    ket_qua = pd.concat([ket_qua, matching_address])
                    ket_qua = pd.concat([ket_qua, phonenum_map])
                    st.markdown('<h3 style="display:flex; align-items:center;">&cir; Summary:</h3>', unsafe_allow_html=True)
                    st.dataframe(ket_qua)
                    
                left_col, center_col, right_col = st.columns([1, 3, 1])
                left_col.markdown("------------")
                right_col.markdown("------------")
                center_col.subheader("The store mapping process is done")
                                            
        
if __name__ == '__main__':
    main()