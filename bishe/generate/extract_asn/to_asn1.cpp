#include <iostream>

#include <fstream>

#include <string>

#include <vector>

using namespace std;

int main()

{

    std::string output_file;

    std::string input_file = "/home/lab221/Projects/bishe/36331-j00-txt目录/36331-j00-修改乱码-删除无关block-删除SetupRelease.txt";

    std::cout << input_file.c_str() << std::endl;

    int pos = input_file.find('.');

    if (pos == std::string::npos)

    {

        output_file = input_file + ".asn";
    }

    else

    {

        output_file = input_file.substr(0, pos) + ".asn";
    }

    std::fstream input;

    input.open(input_file.c_str(), std::fstream::in);

    if (input.fail() == true)

    {

        std::cout << "Please check input file is correct !" << std::endl;

        return 1;
    }

    std::fstream output;

    output.open(output_file.c_str(), std::fstream::out);

    if (output.fail() == true)

    {

        std::cout << "The output file can not be created here !" << std::endl;

        return 1;
    }

    std::string input_line;

    std::vector<std::string> vec_asn;

    std::vector<std::string>::iterator itr;

    const unsigned long cul_asn_idle = 0x0;

    const unsigned long cul_asn_start = 0x1;

    unsigned long asn_state = cul_asn_idle;

    while (std::getline(input, input_line))

    {

        if (cul_asn_idle == asn_state)

        {

            if (input_line.find("-- ASN1START") != std::string::npos)

            {

                asn_state |= cul_asn_start;
            }

            continue;
        }

        if (0 != (cul_asn_start & asn_state))

        {

            if (input_line.find("-- ASN1STOP") != std::string::npos)

            {

                asn_state = cul_asn_idle;
            }

            else

            {

                vec_asn.push_back(input_line);
            }
        }
    }

    for (itr = vec_asn.begin(); itr != vec_asn.end(); ++itr)

    {

        output << *itr << std::endl;
    }

    input.close();

    output.close();

    return 0;
}