import cv2
import sys
import numpy as np
import os 
import ldpc

BLOCK_WIDTH = 11
BLOCK_HEIGHT = 11
BYTES_FOR_MSG_LEN = 3


BITS_FOR_MSG_LEN = 8*BYTES_FOR_MSG_LEN

BITS_FOR_MSG_ECC_FUNC_BY_LEN = lambda msg_length: int(np.ceil((8*msg_length+BITS_FOR_MSG_LEN)/ldpc.input_chunk_size)*ldpc.encoded_chunk_size)

# 0 <-> Negative Value 
# 1 <-> Positive Value
bit_enc = lambda x: -1 if x==0 else 1
bit_dec = lambda x: 0 if x<0 else 1 

# The value that will be changed to embedd the message in a block of size (M,N) is fourier_<color>[block_data_indecies(M,N)]
block_data_indecies = lambda M,N: (M-1, N-1)


if len(sys.argv)!=4:
    print("Error: Mismatching argument format: should be; <image_file_name> -i <text_file_to_embedd>(optional) -o <text_file_to_extract_to>(optional)")
    sys.exit(1)

image = cv2.imread(sys.argv[1])
if image is None:
    print("Error: Couldn't read image")
    sys.exit(1)

def string_to_bits(s):
    return (np.frombuffer(s.encode("ascii"), dtype="u1") - 48)

def bytes_to_bits(byte_array):
    return [int(bit) for byte in byte_array for bit in f"{byte:08b}"]

def bin_string_to_bytearray(str):
    return bytearray(int(str[i:i+8], 2) for i in range(0, len(str), 8))

def len_and_bytes_to_bits(msg):
    bits = np.concatenate((string_to_bits(bin(len(msg))[2:].zfill(BITS_FOR_MSG_LEN)), bytes_to_bits(msg)))
    return ldpc.encode(bits)


def choose_ENC_FREQ_MAG(image, bits):
    best_mag = 90
    min_dist = -1
    for mag in range(5000,99,-4):
        enc_image=encode_6_bits(image, bits, mag)
        #if enc_image==None:
         #   print("Skipping option, not in [0,255]")
          #  continue
        dec_bits = decode_6_bits(enc_image)
        cur_dist = 0 
        for i in range(6):
            if bits[i]!=dec_bits[i]:
                cur_dist=cur_dist+1
        if min_dist<0 or cur_dist < min_dist:
            best_mag=mag
            min_dist=cur_dist
        if min_dist==0:
            break 
    return best_mag 



def encode_6_bits(image, bits, ENC_FREQ_MAG):
    M, N, _ = image.shape
    b, g, r = cv2.split(image)

    fourier_b = np.fft.fft2(b)
    fourier_g = np.fft.fft2(g)
    fourier_r = np.fft.fft2(r)
    
    i, j = block_data_indecies(M,N)
    fourier_b[i][j] = complex(bit_enc(bits[0])*ENC_FREQ_MAG, bit_enc(bits[1])*ENC_FREQ_MAG)
    fourier_g[i][j]= complex(bit_enc(bits[2])*ENC_FREQ_MAG, bit_enc(bits[3])*ENC_FREQ_MAG)
    fourier_r[i][j] = complex(bit_enc(bits[4])*ENC_FREQ_MAG, bit_enc(bits[5])*ENC_FREQ_MAG)

    ifourier_b = np.fft.ifft2(fourier_b)
    ifourier_g = np.fft.ifft2(fourier_g)
    ifourier_r = np.fft.ifft2(fourier_r)

    return cv2.merge((
        np.abs(ifourier_b).astype(np.uint8),
        np.abs(ifourier_g).astype(np.uint8),
        np.abs(ifourier_r).astype(np.uint8)
    ))

def decode_6_bits(image):
    M, N, _ = image.shape
    b, g, r = cv2.split(image)

    fourier_b = np.fft. fft2(b)
    fourier_g = np.fft.fft2(g)
    fourier_r = np.fft.fft2(r)

    i, j = block_data_indecies(M,N)
    return [bit_dec(fourier_b[i][j].real), bit_dec(fourier_b[i][j].imag),
            bit_dec(fourier_g[i][j].real), bit_dec(fourier_g[i][j].imag),
            bit_dec(fourier_r[i][j].real), bit_dec(fourier_r[i][j].imag)]


def embedd_msg(image, msg):
    M, N, _ = image.shape

    if int(np.log2(8*len(msg)))+1>BITS_FOR_MSG_LEN:
        print("Error: " + str(int(np.log2(8*len(msg)))+1) + " bits are needed to represent the length of the message but " + str(BITS_FOR_MSG_LEN) + " is the limit")
        sys.exit(1)

    bits_capacity = int(M/BLOCK_HEIGHT)*int(N/BLOCK_WIDTH)*6
    bits_required = BITS_FOR_MSG_ECC_FUNC_BY_LEN(len(msg))
    if bits_required>bits_capacity:
        print("Error: " + str(bits_required) + " bits to embedd with capacity of " + str(bits_capacity))
        sys.exit(1)

    #print("".join(len_and_string_to_bits(msg)))
    print("Encoding using ldpc with magnitude brute-forcing...")
    bits_itr = iter(len_and_bytes_to_bits(msg))
    print("Embedding message in image using FFT-2D...")
    for i in range(0, M, BLOCK_HEIGHT):
        for j in range(0, N, BLOCK_WIDTH):
            k=0
            cur_bits=[0,0,0,0,0,0]
            try: 
                while k<6:
                    cur_bits[k] = next(bits_itr)
                    k=k+1
            except StopIteration:
                k=-1
                
            image_block = image[i:min(i+BLOCK_HEIGHT,M), j:min(j+BLOCK_WIDTH, N)]
            #print("".join(cur_bits), end="")
            image[i:min(i+BLOCK_HEIGHT,M), j:min(j+BLOCK_WIDTH, N)] = encode_6_bits(image_block, cur_bits, choose_ENC_FREQ_MAG(image_block, cur_bits))

            if k<0:
                print("Encoded message embedded")
                return
                

def extract_msg(image):
    retreived_bits = 0
    msg_len = -1
    msg_bits = []
    M, N, _ = image.shape
    for i in range(0, M, BLOCK_HEIGHT):
        for j in range(0, N, BLOCK_WIDTH):
            image_block = image[i:min(i+BLOCK_HEIGHT,M), j:min(j+BLOCK_WIDTH, N)]
            msg_bits.extend(decode_6_bits(image_block))
            retreived_bits+=6
            if msg_len<0 and len(msg_bits)>=ldpc.encoded_chunk_size:
                first_chunk = ldpc.decode(msg_bits[:ldpc.encoded_chunk_size])  
                msg_len = int("".join(map(str,first_chunk[:BITS_FOR_MSG_LEN])),2)
                
            if msg_len>=0 and BITS_FOR_MSG_ECC_FUNC_BY_LEN(msg_len)<=retreived_bits:
                print("Encoded bits were extracted from the image")
                return bin_string_to_bytearray("".join(map(str,ldpc.decode(msg_bits)[BITS_FOR_MSG_LEN:msg_len*8+BITS_FOR_MSG_LEN])))
            
    print("Error: Not enough bits were hidden")
    sys.exit(1)

if sys.argv[2]=="-o":
    try:
        with open(sys.argv[3], "wb") as output_file:
            output_file.write(extract_msg(image))
            print("Message bits were succesfully decoded and written")
    except FileNotFoundError:
        print("Error: file " + sys.argv[2] + " not found")
        sys.exit(1)
    except Exception as e:
        print(f"Exctraction Error: {e}")

elif sys.argv[2]=="-i":
    try:
        with open(sys.argv[3], "rb") as input_file:
            input_bytes = input_file.read()
    except FileNotFoundError:
        print("Error: file " + sys.argv[2] + " not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
    embedd_msg(image, input_bytes)
    # Save the edited image as a BMP file
    original_name, file_extension = os.path.splitext(sys.argv[1])
    output_file_name = original_name + "_s.bmp"
    cv2.imwrite(output_file_name, image)

