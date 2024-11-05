mkdir -p result
for i in {1..17} ; do python src/opencv_test/__init__.py bench/$i.jpg ; mv output.jpg result/$i.jpg ; done
