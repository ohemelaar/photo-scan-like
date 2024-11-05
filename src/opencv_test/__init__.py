import cv2 as cv
import numpy as np
import sys

MEDIAN_SIZE = 51
BLUR_SIZE = 301
CONTRAST_OVERSHOOT = 1.05 # 5%
MODE = "save"
# MODE = "view"


def tou8(img):
    return np.astype(img, np.uint8)


def tof32(img):
    return np.astype(img, np.float32)


def tobgr(img):
    return cv.cvtColor(img, cv.COLOR_GRAY2BGR)


def clamp(img):
    return np.minimum(img, 255)


img = cv.imread(sys.argv[1])

whitebalancer = cv.xphoto.createGrayworldWB()

white_balanced = whitebalancer.balanceWhite(img)
# minimum channel trick
# at this point all the paper in the image should be some shade of gray, meaning all channels should be equal
# any color (difference between channels) makes the paper darker.
# For example red color means blue and green channels are lower, while red channel is still at same (ish) level as paper
# so to get a closer approximation of the "real gray" produced by the paper, we only keep the lightest channel
# doing so we avoid correcting brightness too much in lightly colored areas
#
# is there a better way to do this (maybe in hsv or hls)?
r, g, b = cv.split(white_balanced)
gray = cv.max(cv.max(r, g), b)

_, sat, _ = cv.split(cv.cvtColor(white_balanced, cv.COLOR_BGR2HSV))
# _, _, sat = cv.split(cv.cvtColor(white_balanced, cv.COLOR_BGR2HLS))

_, sat_mask = cv.threshold(sat, 0, 255, cv.THRESH_OTSU + cv.THRESH_BINARY_INV)


# the idea of these next steps it to replace areas of the image where saturation is too high (likely to be image/text)
# with surrounding color (likely to be paper). To do so we use blurring with an alpha channel, then ditch the alpha
# to only keep the lightness. This is done on the gray image which will be used to correct "shadows" at the end

masked_out_bg = cv.bitwise_and(
    gray, gray, mask=sat_mask
)  # mask out highly saturated areas
# blurring is best done with floats as it keeps more precision for later operations
# especially the alpha demultiply step where small values can be devided by small values
bg_f32 = tof32(masked_out_bg)
mask_f32 = tof32(sat_mask)
# blurring background and mask separately with same parameters
# could probably be done in one go with a rgba but then two channels would be computed for no reason
bg_f32_blur = cv.blur(bg_f32, (BLUR_SIZE, BLUR_SIZE))
mask_f32_blur = cv.blur(mask_f32, (BLUR_SIZE, BLUR_SIZE))
# if we want the blurring to not be impacted by the masked out areas, we need to consider it as a premultiplied result
# which we then divide by the blurred alpha to get more "stable" values on blur alpha edges
bg_f32_blur_alpha_demultiplied = bg_f32_blur * 255 / mask_f32_blur
bg_blur_alpha_demultiplied = tou8(bg_f32_blur_alpha_demultiplied)
# compositing the original image with the blurred result where saturation is too high (mask)
masked_in_bg_blur = cv.bitwise_and(
    bg_blur_alpha_demultiplied, bg_blur_alpha_demultiplied, mask=255 - sat_mask
)
blur_filled = masked_in_bg_blur + masked_out_bg

# thresholding on the gray/blurred composite to clamp dark areas (likely to be text)
#
# both threshold techniques have advantages and drawbacks, depending on the source image. How to pick the best one?
# maybe have several options?
# percentile = np.percentile(blur_filled, 10)
# _, filled_bg_thresh_inv = cv.threshold(
#     255 - blur_filled, percentile, 255, cv.THRESH_TRUNC
# )
_, filled_bg_thresh_inv = cv.threshold(255 - blur_filled, 0, 255, cv.THRESH_TRUNC + cv.THRESH_OTSU)

filled_bg_thresh = 255 - filled_bg_thresh_inv
# applying median blur to remove small detail (likely to be text)
shadow = cv.medianBlur(filled_bg_thresh, MEDIAN_SIZE)

# correcting brightness/contrast in f32 because we're going to have values between 0 and 1 sometimes
shadow_f32 = tof32(tobgr(shadow))
wb_f32 = tof32(white_balanced)
# the reasonning is the following:
# we have a pixel value, which can be eg dark (text) or gray (paper) in the same region
# being in the same region, the "shadow" layer tells us that both pixel have a gray "shadow" value
# so for paper to be white in this area, it needs to be 255. At the same time, text should be bightened proportionnally
# so we divide the image value by shadow and multiply by 255
# we also add a few percent to "overshoot" which gets rid of some noise in white areas
result_excess = (wb_f32 / shadow_f32 * 255) * CONTRAST_OVERSHOOT
# we need to keep the values at 255 max, else we get artifacts when converting back to u8
result_f32 = np.minimum(result_excess, 255)
result = tou8(result_f32)
# manually computed contrast factor to compare
# man = tou8(clamp(tof32(white_balanced) * 2.1))
man = tou8(clamp(tof32(white_balanced) * 1.9))


concat = [
    img,
    result,
    tobgr(shadow),
]
compare = np.concat(concat, axis=1)

if MODE == "view":
    window = cv.namedWindow("view", cv.WINDOW_NORMAL)
    cv.imshow("view", compare)
    k = None
    while k != 27:
        k = cv.waitKey(0)
elif MODE == "save":
    cv.imwrite("output.jpg", compare)
