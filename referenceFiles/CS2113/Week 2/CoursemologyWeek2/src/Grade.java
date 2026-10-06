public class Grade {
    public static double getGradeCap(String grade) {
        double cutoff = 0.0;
        switch (grade) {
            case "A+":
            case "A":
                cutoff = 5.0;
                break;
            case "A-":
                cutoff = 4.5;
                break;
            case "B+":
                cutoff = 4.0;
                break;
            case "B":
                cutoff = 3.5;
                break;
            case "B-":
                cutoff = 3.0;
                break;
            case "C":
                cutoff = 2.5;
                break;
            default:
        }
        return cutoff;
    }

    public static void main(String[] args) {
        System.out.println("A+: " + getGradeCap("A+"));
        System.out.println("B : " + getGradeCap("B"));
    }
}