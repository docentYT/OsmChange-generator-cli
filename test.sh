#!/bin/bash

# this script read .test files from $sample_dir (or a subset, specified as argument)
# which contains the following vars :
#
# tag=<tag to match features and create pairs>
# opts=<options like --create>
# input=<input file>
# ref=<reference file>
# valid_output=<.osc file which must be generated given current parameters>
#
# It then run the main program and compare the created .osc file with $valid_output file

exec_cmd="python ./src/osmchange_generator_cli/main.py"
sample_dir="./example"
result_dir="$sample_dir/result/$(date +%F-%T)"

mkdir -p "$result_dir"
echo "test results in $result_dir"

for f in "$sample_dir/"*"$1"*.test
do
	name=$(basename -s .test "$f")
	# defined in .test file
	tag=
	opts=
	input=
	ref=
	valid_output=
	source "$f"
	echo " ---- $name, tag: $tag, opts: $opts"
	$exec_cmd $opts \
		"$sample_dir/$input" "$sample_dir/$ref" \
		"$result_dir/$name.osc" \
		"$tag" \
		>> "$result_dir/log" 2>&1
	diff -q "$result_dir/$name.osc" "$sample_dir/$valid_output" || echo "FAILED"
done
