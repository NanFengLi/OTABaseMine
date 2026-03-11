# 仅仅是用来检验的工具
def hex_to_bin(hex_str):
	hex_str = hex_str.strip().replace('0x', '').upper()
	try:
		num_bits = len(hex_str) * 4
		bin_str = bin(int(hex_str, 16))[2:].zfill(num_bits)
		bin_str_spaced = ' '.join([bin_str[i:i+8] for i in range(0, len(bin_str), 8)])
		print(f"16进制: {hex_str} -> 2进制: {bin_str_spaced}")
		return bin_str_spaced
	except ValueError:
		print("输入不是有效的16进制字符串")
		return None

if __name__ == "__main__":
	hex_input = "02440400100401f1c91de0d56def2458b4bb604038b9b9dc0cd0347995bd359c5b59c394b23e7ef0"  # 修改这里的16进制字符串
	hex_to_bin(hex_input)
